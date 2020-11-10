from setuptools import setup

# read the contents of your README file
from os import path
this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='pys3sync',
    version='0.1.2',
    author="Angad Singh",
    author_email="angad@angadsingh.in",
    description="Continuously Sync local files to/from S3",
    long_description=long_description,
    long_description_content_type='text/markdown',
    license="MIT",
    url="https://github.com/angadsingh/s3sync",
    py_modules=['s3sync'],
    install_requires=[
        'click',
        'click_log',
        'watchdog',
        'pyyaml',
        'token-bucket',
        'pyformance'
    ],
    entry_points='''
        [console_scripts]
        s3sync=s3sync:cli
    ''',
    classifiers=[
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 3',
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=2.7'
)
