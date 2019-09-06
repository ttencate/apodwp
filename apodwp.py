#!/usr/bin/env python

'''
Web server that serves the latest NASA Astronomy Picture of the Day (APOD) as a
resized PNG image for use as a dynamic desktop background (wallpaper). Usage:

    /latest.png?width=1920&height=1200

'''

import argparse
import hashlib
import io
import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from gevent.pywsgi import WSGIServer
from PIL import Image
import requests


def get_image_data(width, height):
    apod_url = 'https://apod.nasa.gov/apod/'
    logging.info('Fetching APOD home page: %s', apod_url)
    html_response = requests.get(apod_url)
    html_response.raise_for_status()

    logging.info('Processing HTML')
    soup = BeautifulSoup(html_response.text, features='html.parser')
    img_url = None
    for img in soup.find_all('img'):
        if img.parent.name == 'a' and 'href' in img.parent.attrs:
            img_url = img.parent.attrs['href']
            break
    if not img_url:
        raise RuntimeError('No image link found')
    abs_img_url = urljoin('https://apod.nasa.gov/', img_url)
    logging.info('Discovered image URL: %s', abs_img_url)

    abs_img_url_hash = hashlib.sha1()
    abs_img_url_hash.update(abs_img_url.encode('utf-8'))
    cache_file_name = '/tmp/%s.cache' % (abs_img_url_hash.hexdigest())
    try:
        logging.info('Trying to read from cache: %s', cache_file_name)
        with open(cache_file_name, 'rb') as f:
            img = Image.open(f)
            img.load()
    except IOError as ex:
        logging.info('Image not found in cache, fetching image URL: %s', abs_img_url)
        img_response = requests.get(abs_img_url)
        img = Image.open(io.BytesIO(img_response.content))
        img.load()
        logging.info('Writing to cache: %s', cache_file_name)
        with open(cache_file_name, 'wb') as f:
            f.write(img_response.content)

    logging.info('Incoming image size is %dx%d', img.width, img.height)
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
    logging.info('Cropping image to %dx%d (starting at %dx%d)', crop_width, crop_height, crop_left, crop_upper)
    img = img.crop((crop_left, crop_upper, crop_left + crop_width, crop_left + crop_height))
    logging.info('Resizing image to %dx%d', width, height)
    img = img.resize((width, height), Image.LANCZOS)

    logging.info('Encoding image')
    img_data = io.BytesIO()
    img.save(img_data, 'png')
    return img_data.getvalue()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Fetch Astronomy Picture of the Day')
    parser.add_argument('-W', '--width', type=int, help='width of output image in pixels')
    parser.add_argument('-H', '--height', type=int, help='height of output image in pixels')
    parser.add_argument('-o', '--output_file', type=str, help='file to write output PNG image to')
    parser.add_argument('--debug', action='store_true', help='enable debug logging')
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.WARNING)

    data = get_image_data(args.width, args.height)
    with open(args.output_file, 'wb') as f:
        f.write(data)
