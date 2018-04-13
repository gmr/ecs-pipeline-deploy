ECS Deploy
==========
An opinionated deployment application for ECS services.

On execution ecs-pipeline-deploy will examine the current task definition in
the cluster for the current service.

If the tags are different it will:

1. Modify the existing task definition replacing the image in the task definition
2. Update the service to use the new task definition
3. Optionally wait for the new tag to be up and running and all other task
   definitions for the service to stop.

If the tags are the same it will optionally redeploy the service if ``--redeploy`` was specified;
**or** optionally copy the task definition to a new one and deploy as if the tags were different with the `—force` argument;
**or** exit in error if the image tags match and neither ``--redeploy`` nor ``--force`` was specified.

Usage
-----
.. code::

    usage: ecs-deploy [-h] [-f] [-k] [-r] [-w] [-o] [-d DELAY] [-v]
                      [CLUSTER] [SERVICE] [IMAGE]

    Opinionated ECS deployment made easy

    positional arguments:
      CLUSTER               The ECS cluster name to deploy in (default: None)
      SERVICE               The ECS Service name to deploy (default: None)
      IMAGE                 The Docker image (with tag) to deploy for finding the
                            task definition (default: None)

    optional arguments:
      -h, --help            show this help message and exit
      -f, --force           Create a new task definition for the image even if one
                            already exists for the tagged version (default: False)
      -r, --redeploy        Force a redeployment if the tagged images match
                            (default: False)
      -w, --wait            Wait for running tasks to be replaced (default: False)
      -o, --only-new        If waiting, wait for only newly deployed tasks to be
                            running (default: False)
      -d DELAY, --delay DELAY
                            Seconds to delay before checking tasks while waiting
                            on a deployment to finish (default: 5)
      -v, --verbose
