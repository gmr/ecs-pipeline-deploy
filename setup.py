try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

requirements = ['boto3']

setup(name='ecs-pipeline-deploy',
      version='0.1.1',
      classifiers=[
          'Development Status :: 3 - Alpha',
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
          'Programming Language :: Python :: 2',
          'Programming Language :: Python :: 2.7',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.2',
          'Programming Language :: Python :: 3.3',
          'Programming Language :: Python :: Implementation :: CPython',
          'Programming Language :: Python :: Implementation :: PyPy'],
      description='An opinionated deployment application for ECS services',
      long_description=open('README.rst').read(),
      license=open('LICENSE').read(),
      author='Gavin M. Roy',
      author_email='gavinmroy@gmail.com',
      py_modules=['ecs_pipeline_deploy'],
      package_data={'': ['LICENSE', 'README.rst']},
      install_requires=requirements,
      zip_safe=True,
      entry_points={
          'console_scripts': ['ecs-pipeline-deploy=ecs_pipeline_deploy:main']
      })
