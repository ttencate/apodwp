#!/usr/bin/env python3

'''
Fetches the latest NASA Astronomy Picture of the Day (APOD) as a resized PNG
image for use as a dynamic desktop background (wallpaper). Usage: see
README.md.
'''

import argparse
import datetime
import hashlib
import io
import logging
import os.path
import re
import subprocess
import sys
import urllib.parse

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
import requests
import requests.adapters


def wrap_text(width, text, font, **kwargs):
    '''
    Wraps the given text at whitespace to fit inside the given width.
    Returns the given text with newlines added.
    '''
    lines = []
    split_re = re.compile(r'\s+')
    paragraphs = text.split('\n')
    for text in paragraphs:
        split_start = 0
        split_end = 0
        while text:
            split_match = split_re.search(text, pos=split_end)
            next_length = split_match.start() if split_match else len(text)
            (next_left, _, next_right, _) = font.getbbox(text[:next_length], **kwargs)
            ship_line = False
            if next_right - next_left <= width and split_match:
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


def fetch(url):
    with requests.Session() as session:
        retry = requests.adapters.Retry(
            total=5,
            backoff_factor=1.0,
            status_forcelist=[413, 429, 500, 502, 503, 504])
        session.mount('https://', requests.adapters.HTTPAdapter(max_retries=retry))
        response = session.get(url)
        response.raise_for_status()
        return response


def get_image(date=None):
    '''
    Fetches and caches the image for the given date.
    Returns a tuple (image, explanation).
    '''

    if date:
        apod_url = 'https://apod.nasa.gov/apod/ap%s.html' % date.strftime('%y%m%d')
    else:
        apod_url = 'https://apod.nasa.gov/apod/'
        
    logging.info('Fetching APOD home page: %s', apod_url)
    html_response = fetch(apod_url)

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
        img_response = fetch(abs_img_url)
        img = Image.open(io.BytesIO(img_response.content))
        img.load()
        logging.debug('Converting image from mode %s to RGB', img.mode)
        img = img.convert('RGB')
        logging.debug('Writing to cache: %s', cache_file_name)
        with open(cache_file_name, 'wb') as f:
            f.write(img_response.content)
    logging.debug('Incoming image size is %dx%d', img.width, img.height)
    return (img, explanation)


def cover_image(img, width, height):
    '''
    Crops and resizes the image to cover a rectangle of width × height. Returns
    the new image.
    '''
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
    img = img.crop((crop_left, crop_upper, crop_left + crop_width, crop_upper + crop_height))
    logging.debug('Resizing image to %dx%d', width, height)
    img = img.resize((width, height), Image.Resampling.LANCZOS)
    return img


def fit_image(img, width, height):
    '''
    Resizes the image to fit inside a rectangle of width × height, adding black
    bars as needed. Returns the new image.
    '''
    if width / height > img.width / img.height:
        # Requested size is wider. Black bars left/right.
        fit_width = round(img.width / img.height * height)
        fit_height = height
        fit_left = round((width - fit_width) / 2)
        fit_upper = 0
    else:
        # Requested size is taller. Black bars top/bottom.
        fit_width = width
        fit_height = round(img.height / img.width * width)
        fit_left = 0
        fit_upper = round((height - fit_height) / 2)
    logging.debug('Resizing image to %dx%d', fit_width, fit_height)
    img = img.resize((fit_width, fit_height), Image.Resampling.LANCZOS)
    logging.debug('Pasting image at %dx%d', fit_left, fit_upper)
    out = Image.new(img.mode, (width, height), (0, 0, 0))
    out.paste(img, (fit_left, fit_upper))
    return out


def draw_explanation(img, explanation):
    '''
    Draws the given explanation text into the image. Modifies the image rather
    than returning a new one.
    '''
    logging.debug('Drawing explanation text')
    margin = 30
    padding = 30
    width_percent = 30
    font_size = 22
    line_spacing = 10

    font = ImageFont.truetype(os.path.join(os.path.dirname(__file__), 'Raleway-Regular.ttf'), size=font_size)
    draw = ImageDraw.Draw(img, 'RGBA')

    box_width = int(width_percent / 100 * img.width)
    box_right = img.width - margin
    box_bottom = img.height - margin
    text_width = int(box_width - 2 * padding)
    wrapped_text = wrap_text(text_width, explanation, font)
    text_height = draw.multiline_textbbox((0, 0), wrapped_text, font=font, spacing=line_spacing)[3]
    box_height = text_height + 2 * padding
    box_left = box_right - box_width
    box_top = box_bottom - box_height
    box = (box_left, box_top, box_right - 1, box_bottom - 1)
    logging.debug('Box: %s', box)

    draw.rectangle(box, fill=(0, 0, 0, 192))
    draw.multiline_text((box_left + padding, box_top + padding), wrapped_text, font=font, spacing=line_spacing, fill=(255, 255, 255))


def parse_date(s):
    '''
    Parses a YYYY-MM-DD string into a datetime.date object.
    '''
    return datetime.datetime.strptime(s, '%Y-%m-%d').date()


def detect_screen_size():
    '''
    Tries to detect screen resolution. Returns a tuple (width, height), or None
    if detection failed.
    '''
    try:
        xrandr_output = subprocess.run('xrandr', capture_output=True, check=True).stdout.decode()
    except subprocess.CalledProcessError:
        logging.error('xrandr could not be called. Screen resolution detection works only on Linux; on other systems, you must provide --width and --height manually.')
        sys.exit(1)
    for line in xrandr_output.splitlines():
        if '*' in line:
            width, height = map(int, line.split()[0].split('x'))
            return (width, height)


def set_background(file_name):
    command = ['/usr/bin/feh', '--no-fehbg', '--bg-fill', file_name]
    logging.debug('Setting background: %s', ' '.join(command))
    subprocess.run(command, check=True)


def main():
    parser = argparse.ArgumentParser(description='Fetch Astronomy Picture of the Day')
    parser.add_argument('-W', '--width', type=int, help='width of output image in pixels (default: detect monitor resolution)')
    parser.add_argument('-H', '--height', type=int, help='height of output image in pixels (default: detect monitor resolution)')
    parser.add_argument('-d', '--date', type=parse_date, help='date for which to fetch the image, in YYYY-MM-DD format (default: latest)')
    parser.add_argument('-o', '--output_file', type=str, required=True, help='file to write output image to (PNG format recommended)')
    parser.add_argument('-c', '--cover', action='store_true', help='crop image to fill entire screen, rather than adding black bars')
    parser.add_argument('-s', '--set', action='store_true', help='use feh to set the image as the current background')
    parser.add_argument('--debug', action='store_true', help='enable debug logging')
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.WARNING)

    if not args.width or not args.height:
        (args.width, args.height) = detect_screen_size()

    (img, explanation) = get_image(args.date)
    if args.cover:
        img = cover_image(img, args.width, args.height)
    else:
        img = fit_image(img, args.width, args.height)
    draw_explanation(img, explanation)
    logging.debug('Saving image to %s', args.output_file)
    img.save(args.output_file)

    if args.set:
        set_background(args.output_file)


if __name__ == '__main__':
    main()
