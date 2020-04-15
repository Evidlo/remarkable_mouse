from setuptools import setup
from remarkable_mouse import version

setup(
    name='remarkable-mouse',
    version=version.__version__,
    packages=['remarkable_mouse'],
    author="Evan Widloski",
    author_email="evan@evanw.org",
    description="use reMarkable as a graphics tablet",
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    license="GPLv3",
    keywords="remarkable tablet evdev",
    url="https://github.com/evidlo/remarkable_mouse",
    entry_points={
        'console_scripts': [
            'remarkable-mouse = remarkable_mouse.remarkable_mouse:main',
            'remouse = remarkable_mouse.remarkable_mouse:main'
        ]
    },
    install_requires=[
        'paramiko',
        'libevdev',
        'pynput',
        'screeninfo'
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
    ]
)
