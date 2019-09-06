#!/usr/bin/env python

'''
Web server that serves the latest NASA Astronomy Picture of the Day (APOD) as a
resized PNG image for use as a dynamic desktop background (wallpaper). Usage:

    /latest.png?width=1920&height=1200

'''

import hashlib
import io
import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from flask import Flask, request, make_response
from gevent.pywsgi import WSGIServer
from PIL import Image
import requests

app = Flask(__name__)

@app.route('/latest.png')
def latest():
    try:
        width = int(request.args.get('width', '1920'))
        height = int(request.args.get('height', '1080'))
    except ValueError:
        return ('Width and height must be integers', 400)
    if width > 3840 or height > 3840:
        return ('Too big, run your own server', 400)

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
    response_data = io.BytesIO()
    img.save(response_data, 'png')

    logging.info('Sending response')
    response = make_response(response_data.getvalue())
    response.headers['Content-Type'] = 'image/png'
    return response

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    http_server = WSGIServer(('', 8085), app)
    http_server.serve_forever()
