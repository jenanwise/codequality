from setuptools import find_packages
from setuptools import setup


setup(
    name='codequality',
    version='0.1-dev',
    url='http://github.com/oakwise/codequality',
    description='Simple command line code checking metatool',
    long_description=''.join(open('README')),
    keywords='codequality',
    packages=find_packages('.'),
    entry_points={
        'console_scripts': (
            'codequality = codequality.main:main',
        ),
    },
)
