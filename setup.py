# -*- coding: utf-8 -*-
from setuptools import setup

setup(
    name='django-rq',
    version='0.9.1',
    author='Selwin Ong',
    author_email='selwin.ong@gmail.com',
    packages=['django_rq'],
    url='https://github.com/ui/django-rq',
    license='MIT',
    description='An app that provides django integration for RQ (Redis Queue)',
    long_description=open('README.rst').read(),
    zip_safe=False,
    include_package_data=True,
    package_data={'': ['README.rst']},
    install_requires=['django>=1.5.0', 'rq>=0.5.5'],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ]
)
