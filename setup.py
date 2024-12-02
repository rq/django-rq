# -*- coding: utf-8 -*-
from setuptools import setup

setup(
    name='django-rq',
    version='3.0.0',
    author='Selwin Ong',
    author_email='selwin.ong@gmail.com',
    packages=['django_rq'],
    url='https://github.com/rq/django-rq',
    license='MIT',
    description='An app that provides django integration for RQ (Redis Queue)',
    long_description=open('README.rst').read(),
    zip_safe=False,
    include_package_data=True,
    package_data={
        '': ['README.rst'],
        'rq': ['py.typed'],
    },
    install_requires=['django>=3.2', 'rq>=2', 'redis>=3.5'],
    extras_require={
        'Sentry': ['sentry-sdk>=1.0.0'],
        'testing': [],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)
