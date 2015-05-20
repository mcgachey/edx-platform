"""
Tests for the LTI outcome service handlers, both in outcomes.py and in tasks.py
"""

from django.test import TestCase
from lxml import etree
from mock import patch, MagicMock, ANY
from opaque_keys.edx.keys import CourseKey, UsageKey
from student.tests.factories import UserFactory

from lti_provider.models import GradedAssignment, LtiConsumer, OutcomeService
import lti_provider.outcomes as outcomes
import lti_provider.tasks as tasks


class StoreOutcomeParametersTest(TestCase):
    """
    Tests for the store_outcome_parameters method in outcomes.py
    """

    def setUp(self):
        super(StoreOutcomeParametersTest, self).setUp()
        course_id = 'some/course/id'
        usage_id = 'i4x://some/course/problem/uuid'
        self.user = UserFactory.create()
        self.course_key = CourseKey.from_string(course_id)
        self.usage_key = UsageKey.from_string(usage_id)

    def get_valid_request_params(self):
        """
        Returns a dictionary containing a complete set of required LTI
        parameters.
        """
        return {
            'lis_result_sourcedid': 'sourcedid',
            'lis_outcome_service_url': 'http://example.com/service_url',
            'oauth_consumer_key': 'consumer_key',
            'tool_consumer_instance_guid': 'tool_instance_guid',
            'usage_key': self.usage_key,
            'course_key': self.course_key,
        }

    def test_graded_assignment_created(self):
        params = self.get_valid_request_params()
        outcomes.store_outcome_parameters(params, self.user)
        assignment = GradedAssignment.objects.get(
            lis_result_sourcedid=params['lis_result_sourcedid']
        )
        self.assertEqual(assignment.course_key, self.course_key)
        self.assertEqual(assignment.usage_key, self.usage_key)
        self.assertEqual(assignment.user, self.user)

    def test_outcome_service_created(self):
        params = self.get_valid_request_params()
        outcomes.store_outcome_parameters(params, self.user)
        outcome = OutcomeService.objects.get(
            instance_guid=params['tool_consumer_instance_guid']
        )
        self.assertEqual(outcome.consumer_key, params['oauth_consumer_key'])
        self.assertEqual(
            outcome.lis_outcome_service_url, params['lis_outcome_service_url']
        )

    def test_graded_assignment_references_outcome_service(self):
        params = self.get_valid_request_params()
        outcomes.store_outcome_parameters(params, self.user)
        outcome = OutcomeService.objects.get(
            instance_guid=params['tool_consumer_instance_guid']
        )
        assignment = GradedAssignment.objects.get(
            lis_result_sourcedid=params['lis_result_sourcedid']
        )
        self.assertEqual(assignment.outcome_service, outcome)

    def test_no_duplicate_graded_assignments(self):
        params = self.get_valid_request_params()
        outcomes.store_outcome_parameters(params, self.user)
        outcomes.store_outcome_parameters(params, self.user)
        assignments = GradedAssignment.objects.filter(
            lis_result_sourcedid=params['lis_result_sourcedid']
        )
        self.assertEqual(len(assignments), 1)

    def test_no_duplicate_outcome_services(self):
        params = self.get_valid_request_params()
        outcomes.store_outcome_parameters(params, self.user)
        outcomes.store_outcome_parameters(params, self.user)
        outcome_services = OutcomeService.objects.filter(
            instance_guid=params['tool_consumer_instance_guid']
        )
        self.assertEqual(len(outcome_services), 1)

    def test_no_db_update_for_ungraded_assignment(self):
        params = self.get_valid_request_params()
        del params['lis_result_sourcedid']
        outcomes.store_outcome_parameters(params, self.user)
        self.assertEqual(GradedAssignment.objects.count(), 0)
        self.assertEqual(OutcomeService.objects.count(), 0)

    def test_no_db_update_for_bad_request(self):
        params = self.get_valid_request_params()
        del params['lis_outcome_service_url']
        outcomes.store_outcome_parameters(params, self.user)
        self.assertEqual(GradedAssignment.objects.count(), 0)
        self.assertEqual(OutcomeService.objects.count(), 0)

    def test_db_record_created_without_consumer_id(self):
        params = self.get_valid_request_params()
        del params['tool_consumer_instance_guid']
        outcomes.store_outcome_parameters(params, self.user)
        self.assertEqual(GradedAssignment.objects.count(), 1)
        self.assertEqual(OutcomeService.objects.count(), 1)

    def test_outcome_service_supplemented_with_consumer_id(self):
        params = self.get_valid_request_params()
        del params['tool_consumer_instance_guid']
        outcomes.store_outcome_parameters(params, self.user)
        params = self.get_valid_request_params()
        outcomes.store_outcome_parameters(params, self.user)
        outcome = OutcomeService.objects.get(
            consumer_key=params['oauth_consumer_key']
        )
        self.assertEqual(
            outcome.instance_guid, params['tool_consumer_instance_guid']
        )


class SignAndSendReplaceResultTest(TestCase):
    """
    Tests for the sign_and_send_replace_result method in outcomes.py
    """

    def setUp(self):
        super(SignAndSendReplaceResultTest, self).setUp()
        self.course_id = 'some/course/id'
        course_key = CourseKey.from_string(self.course_id)
        self.usage_id = 'i4x://some/course/problem/uuid'
        usage_key = UsageKey.from_string(self.usage_id)
        self.user = UserFactory.create()
        outcome = OutcomeService(
            lis_outcome_service_url='http://example.com/service_url',
            instance_guid='tool_instance_guid',
            consumer_key='consumer_key',
        )
        outcome.save()
        consumer = LtiConsumer(
            consumer_name='consumer',
            consumer_key='consumer_key',
            consumer_secret='secret'
        )
        consumer.save()
        self.assignment = GradedAssignment(
            user=self.user,
            course_key=course_key,
            usage_key=usage_key,
            outcome_service=outcome,
            lis_result_sourcedid='sourcedid',
        )
        self.assignment.save()

    @patch('requests.post', return_value='response')
    def test_sign_and_send_replace_result(self, post_mock):
        response = outcomes.sign_and_send_replace_result(self.assignment, 'xml')
        post_mock.assert_called_with(
            'http://example.com/service_url',
            data='xml',
            auth=ANY,
            headers={'content-type': 'application/xml'}
        )
        self.assertEqual(response, 'response')

    def test_with_no_consumer_secret(self):
        LtiConsumer.objects.all().delete()
        response = outcomes.sign_and_send_replace_result(self.assignment, 'xml')
        self.assertIsNone(response)


class SendOutcomeTest(TestCase):
    """
    Tests for the send_outcome method in tasks.py
    """

    def setUp(self):
        super(SendOutcomeTest, self).setUp()
        self.course_id = 'some/course/id'
        course_key = CourseKey.from_string(self.course_id)
        self.usage_id = 'i4x://some/course/problem/uuid'
        usage_key = UsageKey.from_string(self.usage_id)
        self.user = UserFactory.create()
        self.points_possible = 10
        self.points_earned = 3
        self.generate_xml_mock = self.setup_patch(
            'lti_provider.outcomes.generate_replace_result_xml',
            'replace result XML'
        )
        self.replace_result_mock = self.setup_patch(
            'lti_provider.outcomes.sign_and_send_replace_result',
            'replace result response'
        )
        self.check_result_mock = self.setup_patch(
            'lti_provider.outcomes.check_replace_result_response',
            True
        )
        outcome = OutcomeService(
            lis_outcome_service_url='http://example.com/service_url',
            instance_guid='tool_instance_guid',
            consumer_key='consumer_key',
        )
        outcome.save()
        self.assignment = GradedAssignment(
            user=self.user,
            course_key=course_key,
            usage_key=usage_key,
            outcome_service=outcome,
            lis_result_sourcedid='sourcedid',
        )
        self.assignment.save()

    def setup_patch(self, function_name, return_value):
        """
        Patch a method with a given return value, and return the mock
        """
        mock = MagicMock(return_value=return_value)
        new_patch = patch(function_name, new=mock)
        new_patch.start()
        self.addCleanup(new_patch.stop)
        return mock

    def test_send_outcome(self):
        tasks.send_outcome(
            self.points_possible,
            self.points_earned,
            self.user.id,
            self.course_id,
            self.usage_id
        )
        self.generate_xml_mock.assert_called_once_with('sourcedid', 0.3)
        self.replace_result_mock.assert_called_once_with(self.assignment, 'replace result XML')

    def test_called_with_no_points_possible(self):
        tasks.send_outcome(
            None,
            self.points_earned,
            self.user.id,
            self.course_id,
            self.usage_id
        )
        assert not self.generate_xml_mock.called
        assert not self.replace_result_mock.called

    def test_called_with_no_points_earned(self):
        tasks.send_outcome(
            self.points_possible,
            None,
            self.user.id,
            self.course_id,
            self.usage_id
        )
        assert not self.generate_xml_mock.called
        assert not self.replace_result_mock.called

    def test_called_with_zero_points_possible(self):
        tasks.send_outcome(
            0,
            0,
            self.user.id,
            self.course_id,
            self.usage_id
        )
        assert not self.generate_xml_mock.called
        assert not self.replace_result_mock.called

    def test_called_with_invalid_score(self):
        tasks.send_outcome(
            2,
            5,
            self.user.id,
            self.course_id,
            self.usage_id
        )
        assert not self.generate_xml_mock.called
        assert not self.replace_result_mock.called


# Pylint doesn't recognize members in the LXML module
# pylint: disable=no-member
class XmlHandlingTest(TestCase):
    """
    Tests for the generate_replace_result_xml and check_replace_result_response
    methods in outcomes.py
    """

    response_xml = """
        <imsx_POXEnvelopeResponse xmlns = "http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0">
          <imsx_POXHeader>
            <imsx_POXResponseHeaderInfo>
              <imsx_version>V1.0</imsx_version>
              <imsx_messageIdentifier>4560</imsx_messageIdentifier>
              <imsx_statusInfo>
                {major_code}
                <imsx_severity>status</imsx_severity>
                <imsx_description>Score for result_id is now 0.25</imsx_description>
                <imsx_messageRefIdentifier>999999123</imsx_messageRefIdentifier>
                <imsx_operationRefIdentifier>replaceResult</imsx_operationRefIdentifier>
              </imsx_statusInfo>
            </imsx_POXResponseHeaderInfo>
          </imsx_POXHeader>
          <imsx_POXBody>
            <replaceResultResponse/>
          </imsx_POXBody>
        </imsx_POXEnvelopeResponse>
    """

    result_id = 'result_id'
    score = 0.25

    @patch('uuid.uuid4', return_value='random_uuid')
    def test_replace_result_message_uuid(self, _uuid_mock):
        xml = outcomes.generate_replace_result_xml(self.result_id, self.score)
        tree = etree.fromstring(xml)
        message_id = tree.xpath(
            '//ns:imsx_messageIdentifier',
            namespaces={'ns': 'http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0'}
        )
        self.assertEqual(len(message_id), 1)
        self.assertEqual(message_id[0].text, 'random_uuid')

    def test_replace_result_sourced_id(self):
        xml = outcomes.generate_replace_result_xml(self.result_id, self.score)
        tree = etree.fromstring(xml)
        sourced_id = tree.xpath(
            '//ns:sourcedId',
            namespaces={'ns': 'http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0'}
        )
        self.assertEqual(len(sourced_id), 1)
        self.assertEqual(sourced_id[0].text, 'result_id')

    def test_replace_result_score(self):
        xml = outcomes.generate_replace_result_xml(self.result_id, self.score)
        tree = etree.fromstring(xml)
        xml_score = tree.xpath(
            '//ns:textString',
            namespaces={'ns': 'http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0'}
        )
        self.assertEqual(len(xml_score), 1)
        self.assertEqual(xml_score[0].text, '0.25')

    def create_response_object(
            self, status, xml,
            major_code='<imsx_codeMajor>success</imsx_codeMajor>'
    ):
        """
        Returns an XML document containing a successful replace_result response.
        """
        response = MagicMock()
        response.status_code = status
        response.text = xml.format(major_code=major_code)
        return response

    def test_response_with_correct_xml(self):
        xml = self.response_xml
        response = self.create_response_object(200, xml)
        self.assertTrue(outcomes.check_replace_result_response(response))

    def test_response_with_bad_status_code(self):
        response = self.create_response_object(500, '')
        self.assertFalse(outcomes.check_replace_result_response(response))

    def test_response_with_character_encoding(self):
        xml = '<?XML version="1.0" encoding="UTF-8"?>' + self.response_xml
        response = self.create_response_object(200, xml)
        self.assertTrue(outcomes.check_replace_result_response(response))

    def test_response_with_invalid_xml(self):
        xml = '<badly>formatted</xml>'
        response = self.create_response_object(200, xml)
        self.assertFalse(outcomes.check_replace_result_response(response))

    def test_response_with_multiple_status_fields(self):
        response = self.create_response_object(
            200, self.response_xml,
            major_code='<imsx_codeMajor>success</imsx_codeMajor>'
                       '<imsx_codeMajor>failure</imsx_codeMajor>'
        )
        self.assertFalse(outcomes.check_replace_result_response(response))

    def test_response_with_no_status_field(self):
        response = self.create_response_object(
            200, self.response_xml,
            major_code=''
        )
        self.assertFalse(outcomes.check_replace_result_response(response))

    def test_response_with_failing_status_field(self):
        response = self.create_response_object(
            200, self.response_xml,
            major_code='<imsx_codeMajor>failure</imsx_codeMajor>'
        )
        self.assertFalse(outcomes.check_replace_result_response(response))
