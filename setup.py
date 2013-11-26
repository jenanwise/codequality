from setuptools import find_packages
from setuptools import setup


setup(
    name='codequality',
    version='0.2-dev',
    url='http://github.com/jenanwise/codequality',
    description='Simple code checking metatool',
    long_description=''.join(open('README.rst')),
    keywords='codequality',
    license='MIT',
    packages=find_packages('.'),
    entry_points={
        'console_scripts': (
            'codequality = codequality.main:main',
        ),
    },
)
