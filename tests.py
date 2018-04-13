# coding=utf-8
import unittest

from ecs_pipeline_deploy import cli


class TestImageParsing(unittest.TestCase):
    IMAGES = {
        'alpine': (None, 'alpine', 'latest'),
        'alpine:3.7': (None, 'alpine', '3.7'),
        'docker.aweber.io/_/alpine:3.7':
            ('docker.aweber.io', '_/alpine', '3.7'),
        'docker.aweber.io/pse/anabroker:0.1.0':
            ('docker.aweber.io', 'pse/anabroker', '0.1.0'),
        'docker.aweber.io:8000/pse/anabroker:latest':
            ('docker.aweber.io:8000', 'pse/anabroker', 'latest')
    }

    def test_parsing_expectations(self):
        for image, expectation in self.IMAGES.items():
            result = cli.ECSPipeline.parse_image(image)
            self.assertEqual(result, expectation)
