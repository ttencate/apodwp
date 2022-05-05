Astronomy Picture of the Day Wallpaper
======================================

This is a Python script that downloads the NASA Astronomy Picture of the Day,
crops and resizes it to a size of your choosing, overlays the explanation text
onto it, saves the result to a file, and sets the file as the desktop wallpaper.

For example, for the
[image of 6 September 2019](https://apod.nasa.gov/apod/ap190906.html):

![Example image](example-2019-09-06.jpg)

Requirements
------------

See the `[tool.poetry.dependencies]` section in `pyproject.toml`. If you have
`poetry` installed (recommended!), simply run:

    poetry install --no-root

This creates a virtualenv with just the right dependencies. To run the script
inside that virtualenv, use:

    poetry run apodwp.py

The `--set` option requires `feh`, used as a background setter.

Usage
-----

Run `./apodwp.py --help` to see the available options.

Installation
------------

I'm using something like this in my `~/.xprofile` to refresh my wallpaper every
time I log in:

    ~/apodwp/apodwp --output_file ~/.apod.png --set
