#!/usr/bin/env python3

'''
Web server that serves the latest NASA Astronomy Picture of the Day (APOD) as a
resized PNG image for use as a dynamic desktop background (wallpaper). Usage:

    /latest.png?width=1920&height=1200

'''

import argparse
import hashlib
import io
import logging
import re
import subprocess
import sys
import urllib.parse

from bs4 import BeautifulSoup
from gevent.pywsgi import WSGIServer
from PIL import Image, ImageDraw, ImageFont
import requests


def wrap_text(width, text, font, **kwargs):
    lines = []
    split_re = re.compile(r'\s+')
    paragraphs = text.split('\n')
    for text in paragraphs:
        split_start = 0
        split_end = 0
        while text:
            split_match = split_re.search(text, pos=split_end)
            next_length = split_match.start() if split_match else len(text)
            next_size = font.getsize(text[:next_length], **kwargs)
            ship_line = False
            if next_size[0] <= width and split_match:
                split_start = split_match.start()
                split_end = split_match.end()
            else:
                if not split_match:
                    split_start = len(text)
                    split_end = len(text)
                lines.append(text[:split_start])
                text = text[split_end:]
                split_start = 0
                split_end = 0
    return '\n'.join(lines)


def get_image_data(width, height):
    apod_url = 'https://apod.nasa.gov/apod/'
    logging.info('Fetching APOD home page: %s', apod_url)
    html_response = requests.get(apod_url)
    html_response.raise_for_status()

    logging.debug('Processing HTML')
    soup = BeautifulSoup(html_response.text, features='html5lib')
    img_url = None
    for img in soup.find_all('img'):
        if img.parent.name == 'a' and 'href' in img.parent.attrs:
            img_url = img.parent.attrs['href']
            break
    if not img_url:
        raise RuntimeError('No image link found')
    abs_img_url = urllib.parse.urljoin('https://apod.nasa.gov/', img_url)
    logging.debug('Discovered image URL: %s', abs_img_url)
    explanation = soup.find('b', text=re.compile('Explanation:')).parent.get_text()
    explanation = re.sub(r'\s+', ' ', explanation).strip()[12:].strip()
    logging.debug('Extracted explanation: %s', explanation)

    abs_img_url_hash = hashlib.sha1()
    abs_img_url_hash.update(abs_img_url.encode('utf-8'))
    cache_file_name = '/tmp/%s.cache' % (abs_img_url_hash.hexdigest())
    try:
        logging.debug('Trying to read from cache: %s', cache_file_name)
        with open(cache_file_name, 'rb') as f:
            img = Image.open(f)
            img.load()
    except IOError as ex:
        logging.info('Image not found in cache, fetching image URL: %s', abs_img_url)
        img_response = requests.get(abs_img_url)
        img = Image.open(io.BytesIO(img_response.content))
        img.load()
        logging.debug('Writing to cache: %s', cache_file_name)
        with open(cache_file_name, 'wb') as f:
            f.write(img_response.content)

    logging.debug('Incoming image size is %dx%d', img.width, img.height)
    if width / height > img.width / img.height:
        # Requested size is wider. Crop top/bottom.
        crop_width = img.width
        crop_height = round(height / width * img.width)
        crop_left = 0
        crop_upper = round((img.height - crop_height) / 2)
    else:
        # Requested size is taller. Crop left/right.
        crop_width = round(width / height * img.height)
        crop_height = img.height
        crop_left = round((img.width - crop_width) / 2)
        crop_upper = 0
    logging.debug('Cropping image to %dx%d (starting at %dx%d)', crop_width, crop_height, crop_left, crop_upper)
    img = img.crop((crop_left, crop_upper, crop_left + crop_width, crop_left + crop_height))
    logging.debug('Resizing image to %dx%d', width, height)
    img = img.resize((width, height), Image.LANCZOS)

    logging.debug('Drawing explanation text')
    margin_bottom = 50
    padding = 20
    font_size = 18
    line_spacing = 10
    font = ImageFont.truetype('Raleway-Regular.ttf', size=font_size)
    draw = ImageDraw.Draw(img, 'RGBA')
    wrapped_text = wrap_text(width - 2 * padding, explanation, font)
    text_height = draw.multiline_textsize(wrapped_text, font=font, spacing=line_spacing)[1]
    box_height = text_height + 2 * padding
    box_top = height - margin_bottom - box_height
    draw.rectangle((0, box_top, width, box_top + box_height), fill=(0, 0, 0, 128))
    draw.multiline_text((padding, box_top + padding), wrapped_text, font=font, spacing=line_spacing, fill=(255, 255, 255))

    logging.debug('Encoding image')
    img_data = io.BytesIO()
    img.save(img_data, 'png')
    return img_data.getvalue()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Fetch Astronomy Picture of the Day')
    parser.add_argument('-W', '--width', type=int, help='width of output image in pixels (default: detect monitor resolution)')
    parser.add_argument('-H', '--height', type=int, help='height of output image in pixels (default: detect monitor resolution)')
    parser.add_argument('-o', '--output_file', type=str, required=True, help='file to write output PNG image to')
    parser.add_argument('--debug', action='store_true', help='enable debug logging')
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.WARNING)

    if not args.width or not args.height:
        try:
            xrandr_output = subprocess.run('xrandr', capture_output=True, check=True).stdout.decode()
        except subprocess.CalledProcessError:
            logging.error('xrandr could not be called. Screen resolution detection works only on Linux; on other systems, you must provide --width and --height manually.')
            sys.exit(1)
        for line in xrandr_output.splitlines():
            if '*' in line:
                args.width, args.height = map(int, line.split()[0].split('x'))

    data = get_image_data(args.width, args.height)
    with open(args.output_file, 'wb') as f:
        f.write(data)
