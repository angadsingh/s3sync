from setuptools import setup

setup(
    name='pys3sync',
    version='0.1',
    author="Angad Singh",
    author_email="angad@angadsingh.in",
    description="Continuously Sync local files to/from S3",
    long_description="""A utility created to sync files to/from S3 as a continuously running
    process, without having to manually take care of managing the sync. 
    It internally uses the aws s3 sync command to do the sync and uses
    python's watchdog listener to get notified of any changes to the watched folder.""",
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