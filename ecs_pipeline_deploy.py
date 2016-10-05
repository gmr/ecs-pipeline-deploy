import argparse
import logging
import sys
import time

import boto3
from botocore import exceptions

__version__ = '0.1.1'

LOGGER = logging.getLogger(__name__)


def deploy_test(client, args):
    """Perform the "test" deployment, which is to cycle through the running
    tasks, stopping them one at a time.

    :param boto3.client client: The boto client for doing things
    :param argparse.namespace args: CLI arguments

    """
    cluster = args.cluster or args.env
    service_arn = _service_arn(client, cluster, args.service[0])
    _prefix, service = service_arn.split('service/')
    return _restart_tasks(client, cluster, service, args.version, args.wait)


def deploy_stage(client, args):
    """Perform the "stage" deployment, grabbing the current test task
    definition, replacing the latest tag with the specified tag, and then
    updating the service to that version.

    If ``force`` is specified, the existing running tasks will be cycled one
    at a time.

    """
    task_definition_arn = _new_task_definition_from_test(
        client, args.service[0], args.tag, args.image)
    service_arn = _service_arn(client, args.env, args.service[0])
    _prefix, service_name = service_arn.split('service/')
    LOGGER.info('Updating %s in %s to run %s', service_name,
                args.env, task_definition_arn.split('/')[-1])
    result = client.update_service(cluster=args.env, service=service_arn,
                                   taskDefinition=task_definition_arn)
    if result['service']['taskDefinition'] == task_definition_arn:
        LOGGER.info('Updated %s in %s to %s', service_name,
                    args.env, task_definition_arn.split('/')[-1])
        if args.wait:
            _restart_tasks(client, args.env, service_name, args.tag, True)
    return True


def deploy_production(client, args):
    """Perform the "stage" deployment, grabbing the current test task
    definition, replacing the latest tag with the specified tag, and then
    updating the service to that version.

    If ``force`` is specified, the existing running tasks will be cycled one
    at a time.

    """
    return True


def parse_cli_args():
    parser = argparse.ArgumentParser(
        prog='ecs-deploy',
        description='Opinionated ECS deployment made easy')
    env = parser.add_subparsers(dest='env')
    test_parser = env.add_parser('test')
    test_parser.add_argument('--version', default='latest',
                             help='The version that is being deployed')
    test_parser.add_argument('-w', '--wait', action='store_true',
                             help='Wait for running tasks to be replaced')
    stage_parser = env.add_parser('stage')
    stage_parser.add_argument('-t', '--tag', required=True)
    stage_parser.add_argument('-w', '--wait', action='store_true',
                              help='Wait for running tasks to be replaced')
    prod_parser = env.add_parser('production')
    prod_parser.add_argument('-t', '--tag', required=True)
    prod_parser.add_argument('--show-tags', action='store_true',
                             help=('Instead of deploying a tagged version, '
                                   'show what tags are available to deploy in '
                                   'production.'))

    prod_parser.add_argument('--version', default='latest',
                             help='The version that is being deployed')
    prod_parser.add_argument('-w', '--wait', action='store_true',
                             help='Wait for running tasks to be replaced')

    parser.add_argument('service', nargs=1,
                        help='The ECS Service name')
    parser.add_argument('-c', '--cluster', action='store', default=None,
                        help='The ECS cluster name')
    parser.add_argument('-i', '--image', action='store',
                        help='The Docker image (without tag) to deploy')
    parser.add_argument('-d', '--debug', action='store_true')
    parser.add_argument('-v', '--verbose', action='store_true')
    return parser.parse_args()


def main():
    args = parse_cli_args()
    level = logging.WARNING
    if args.debug is True:
        level = logging.DEBUG
    elif args.verbose is True:
        level = logging.INFO
    logging.basicConfig(level=level)
    logger = logging.getLogger('botocore.vendored.requests.packages.urllib3')
    logger.setLevel(logging.WARNING)
    try:
        run(args)
    except (exceptions.ClientError, ValueError) as error:
        sys.stderr.write('{}\n'.format(str(error)))
        sys.exit(1)


def run(args):
    client = _ecs_client(args)
    LOGGER.info('Deploying %s %s in %s', args.service[0],
                getattr(args, 'tag', getattr(args, 'version', 'latest')),
                args.cluster or args.env)
    if args.env == 'test':
        deploy_test(client, args)
    elif args.env == 'stage':
        deploy_stage(client, args)
    elif args.env == 'production':
        deploy_production(client, args)


def _ecs_client(args):
    return boto3.client('ecs')


def _image_match(name, service, image):
    parts = name.split('/')
    LOGGER.debug('Evaluating %s against %s', name, image)
    if name == image:  # Exact match on specified name
        return True

    LOGGER.debug('Evaluating %s against %s', parts[-1], service)
    if parts[-1] == service:  # service is the last part of the docker tag
        LOGGER.debug('Matched on %s', parts[-1])
        return True

    composed = '/'.join(parts[-2:])
    LOGGER.debug('Evaluating %s against %s', composed, image)
    if composed == image:
        LOGGER.debug('Matched on %s', composed)
        return True

    LOGGER.debug('Evaluating %s against %s', composed, service)
    if composed == service:
        LOGGER.debug('Matched on %s', composed)
        return True
    return False


def _list_running_tasks(client, cluster, service_name):
    LOGGER.debug('Getting running tasks for %s in the %s cluster',
                 service_name, cluster)
    response = client.list_tasks(cluster=cluster,
                                 serviceName=service_name,
                                 desiredStatus='RUNNING')
    return sorted(response['taskArns'])


def _new_task_definition_from_test(client, service_name, tag, image_name):
    service_arn = _service_arn(client, 'test', service_name)
    task_definition = _task_definition(client, 'test', service_arn)
    for container in task_definition.get('containerDefinitions', []):
        if ':' not in container['image']:
            LOGGER.debug('Skipping non-versioned container: %s', container)
            return False

        name, version = container['image'].split(':')
        LOGGER.info('Processing %s:%s', name, version)

        if not _image_match(name, service_name, image_name):
            LOGGER.debug('Skipping %s due to non-match', container['image'])
            continue

        container['image'] = container['image'].replace(version, tag)

        log_config = container.get('logConfiguration', {})
        options = log_config.get('options', {})
        if 'tag' in options:
            container['logConfiguration']['options']['tag'] = \
                options['tag'].replace(version, tag)

        return _save_task_definition(client, task_definition)
    raise ValueError('No matching Docker images found in the task definition')


def _restart_tasks(client, cluster, service_name, revision,
                   wait_for_replacement):
    old_tasks = _list_running_tasks(client, cluster, service_name)
    LOGGER.info('Restarting %i tasks for %s in %s',
                len(old_tasks), cluster, service_name)
    for task in old_tasks:
        _stop_task(client, cluster, task,
                   'Deployment of {} {}'.format(service_name, revision))
        LOGGER.debug('Waiting for %s to be replaced in %s', task, cluster)
        while wait_for_replacement:
            current_tasks = _list_running_tasks(client, cluster, service_name)
            if len(current_tasks) == len(old_tasks) and \
                    task not in current_tasks:
                LOGGER.debug('%s was replaced', task)
                break
            time.sleep(5)
    LOGGER.info('%i tasks restarted', len(old_tasks))


def _save_task_definition(client, task_definition):
    for key in {'requiresAttributes', 'revision',
                'status', 'taskDefinitionArn'}:
        del task_definition[key]
    LOGGER.debug('Registering new task definition for %s',
                 task_definition['family'])
    result = client.register_task_definition(**task_definition)
    LOGGER.debug('New task definition arn: %s',
                 result['taskDefinition']['taskDefinitionArn'])
    return result['taskDefinition']['taskDefinitionArn']


def _service_arn(client, cluster, name):
    services = _services(client, cluster)
    cfprefix = '{}-{}'.format(cluster, name)
    for arn in services:
        prefix, service_name = arn.split('service/')
        if service_name == name or service_name.startswith(cfprefix):
            return arn
    raise ValueError('Service {} not found in {}'.format(name, cluster))


def _services(client, cluster_name):
    LOGGER.info('Getting services in the %s cluster', cluster_name)
    response = client.list_services(cluster=cluster_name)
    return response['serviceArns']


def _stop_task(client, cluster, task, reason):
    LOGGER.info('Stopping %s in %s', task, cluster)
    client.stop_task(cluster=cluster, task=task, reason=reason)


def _task_definition(client, cluster, service):
    LOGGER.info('Fetching service configuration for %s', service)
    response = client.describe_services(cluster=cluster, services=[service])
    assert len(response['services']) == 1
    arn = response['services'][0]['taskDefinition']
    response = client.describe_task_definition(taskDefinition=arn)
    return response['taskDefinition']


if __name__ == '__main__':
    main()
