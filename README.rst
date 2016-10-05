ECS Deploy
==========
An opinionated deployment application for ECS services.

The stages of the deployment pipeline are:

- test - The test environment represents the state of master in a git repository
    or the ``latest`` tag for a Docker image.
- stage - The stage environment represents a tag in a git repository or a tagged
    revision of a Docker image.
- production - The production environment is deployed using task definitions
    that were created in promoting ``test`` to ``stage``.

``ecs-deploy`` is used in the deployment pipeline for an ECS service. It expects
a stable base task definition that is always running in the ``test``
environment. This task definition should point to the ``latest`` tag for a
Docker image.  If invoked for the ``test`` environment, ``ecs-deploy`` simply
any running tasks.

When invoked for the ``stage`` environment, the current task definition for
the ``test`` environment is downloaded and modified to replace the ``latest``
tag for the Docker image with the specified tag revision.

When invoked for the ``production`` environment, it will update the service
to use a task definition using the specified tag version.
