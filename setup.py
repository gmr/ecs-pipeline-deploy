# coding=utf-8
"""
ECS Pipeline Deploy
===================

"""
from os import path

import setuptools

from ecs_pipeline_deploy import __version__


def read_requirements(name):
    """Return the requirements from the requirements file as a list

    :param str name: The filename
    :rtype: list

    """
    requirements = []
    with open(path.join('requires', name)) as req_file:
        for line in req_file:
            if '#' in line:
                line = line[:line.index('#')]
            line = line.strip()
            if line.startswith('-r'):
                requirements.extend(read_requirements(line[2:].strip()))
            elif line and not line.startswith('-'):
                requirements.append(line)
    return requirements


setuptools.setup(
    name='ecs-pipeline-deploy',
    version=__version__,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Environment :: MacOS X',
        'Environment :: No Input/Output (Daemon)',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Operating System :: MacOS',
        'Operating System :: POSIX',
        'Operating System :: POSIX :: BSD',
        'Operating System :: POSIX :: Linux',
        'Operating System :: Unix',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy'],
    description='An opinionated deployment application for ECS services',
    long_description=open('README.rst').read(),
    license='BSD',
    author='Gavin M. Roy',
    author_email='gavinmroy@gmail.com',
    packages=['ecs_pipeline_deploy'],
    package_data={'': ['LICENSE', 'README.rst']},
    install_requires=read_requirements('installation.txt'),
    zip_safe=True,
    entry_points={
        'console_scripts': ['ecs-pipeline-deploy=ecs_pipeline_deploy.cli:main']
    })
