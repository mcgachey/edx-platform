from django.core.exceptions import ObjectDoesNotExist
import logging
from lxml import etree
from lxml.etree import ParseError
import requests
from requests_oauthlib import OAuth1
import uuid

import lti_provider.models
from lti_provider.lti_utils import parse_course_and_usage_keys

log = logging.getLogger("edx.lti_provider")


def store_outcome_parameters(request_params, user):
    result_id = request_params.get('lis_result_sourcedid', None)
    # We're only interested in requests that include a lis_result_sourcedid
    # parameter. An LTI consumer that does not send that parameter does not
    # expect scoring updates for that particular request.
    if result_id:
        result_service = request_params.get('lis_outcome_service_url', None)
        if not result_service:
            # TODO: There may be a way to recover from this error; if we know
            # the LTI consumer that the request comes from then we may be able
            # to figure out the result service URL. As it stands, though, this
            # is a badly-formed LTI request
            log.warn(
                "Outcome Service: lis_outcome_service_url parameter missing "
                "from scored assignment; we will be unable to return a score. "
                "Request parameters: $s",
                request_params
            )
            return

        # We need to identify which tool consumer made the request. The best way
        # to do this is to use the tool_consumer_instance_guid, which should be
        # unique for each tool consumer. Unfortunately, that LTI parameter is
        # optional, so we can't rely on it being available. In that case, we can
        # fall back on the consumer key as a means of identifying the consumer.
        # Note that this depends on every consumer being assigned a unique key
        # (which is best practice anyway).
        instance_guid = request_params.get('tool_consumer_instance_guid', None)
        consumer_key = request_params.get('oauth_consumer_key', None)
        assert consumer_key, "oauth_consumer_key is not an optional parameter."

        # Both usage and course ID parameters are supplied in the LTI launch URL
        usage_key = request_params.get('usage_key', None)
        course_key = request_params.get('course_key', None)
        assert usage_key and course_key, \
            "usage_key {} and course_key {} should not be None".format(
                usage_key, course_key
            )

        # Create a record of the outcome service if necessary
        outcomes, __ = lti_provider.models.OutcomeService.objects.get_or_create(
            lis_outcome_service_url=result_service,
            consumer_key=consumer_key
        )
        # There could be a case where an earlier launch registered the outcome
        # service but did not have the consumer instance guid available, in
        # which case the outcome service would only have the consumer key
        # available. If we now have better information, we can improve that
        # record.
        if instance_guid and not outcomes.instance_guid:
            outcomes.instance_guid = instance_guid
            outcomes.save()

        # Create a record for this assignment. Note that there may already
        # be a record, if this assignment has been launched more than once
        # by the same user/tool consumer combination.
        lti_provider.models.GradedAssignment.objects.get_or_create(
            lis_result_sourcedid=result_id,
            course_key=course_key,
            usage_key=usage_key,
            user=user,
            outcome_service=outcomes
        )


def send_outcome(points_possible, points_earned, user_id, course_id, usage_id):
    course_key, usage_key = parse_course_and_usage_keys(course_id, usage_id)
    if not all(course_key, usage_key):
        log.error(
            "Outcome Service: Invalid course ID (%s) or usage ID (%s)",
            course_id, usage_id
        )
        return

    # Calculate the user's score, on a scale of 0.0 - 1.0.
    if points_possible == 0:
        score = 0.0
    else:
        score = points_earned / points_possible

    try:
        assignment = lti_provider.models.GradedAssignment.objects.get(
            user=user_id, course_key=course_key, usage_key=usage_key
        )
    except ObjectDoesNotExist:
        # The user/course/usage combination does not relate to a previous graded
        # LTI launch. This can happen if an LTI consumer embeds some gradable
        # content in a context that doesn't require a score (maybe by including
        # an exercise as a sample that students may complete but don't count
        # towards their grade).
        return

    xml = generate_replace_result_xml(assignment.lis_result_sourcedid, score)
    response = sign_and_send_replace_result(assignment, xml)
    if not (response and check_replace_result_response(response)):
        log.error(
            "Outcome Service: Failed to update score on LTI consumer. "
            "User: %s, course: %s, usage: %s, score: %s, possible: %s "
            "status: %s, body: %s",
            user_id,
            course_key,
            usage_key,
            points_earned,
            points_possible,
            response,
            response.text
        )


def generate_replace_result_xml(result_sourcedid, score):
    envelope = etree.Element('imsx_POXEnvelopeRequest',
        xmlns='http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0')
    header = etree.SubElement(envelope, 'imsx_POXHeader')
    header_info = etree.SubElement(header, 'imsx_POXRequestHeaderInfo')
    version = etree.SubElement(header_info, 'imsx_version')
    message_id = etree.SubElement(header_info, 'imsx_messageIdentifier')
    body = etree.SubElement(envelope, 'imsx_POXBody')
    replace_result_request = etree.SubElement(body, 'replaceResultRequest')
    result_record = etree.SubElement(replace_result_request, 'resultRecord')
    sourced_guid = etree.SubElement(result_record, 'sourcedGUID')
    sourced_id = etree.SubElement(sourced_guid, 'sourcedId')
    result = etree.SubElement(result_record, 'result')
    result_score = etree.SubElement(result, 'resultScore')
    language = etree.SubElement(result_score, 'language')
    text_string = etree.SubElement(result_score, 'textString')

    version.text = 'V1.0'
    message_id.text = str(uuid.uuid4())
    sourced_id.text = result_sourcedid
    language.text = 'en'
    text_string.text = str(score)

    return etree.tostring(envelope, xml_declaration=True, encoding='UTF-8')


def sign_and_send_replace_result(assignment, xml):
    outcome_service = assignment.outcome_service
    assert outcome_service, 'assignment.outcome_service guaranteed to be non-null'
    consumer_key = outcome_service.consumer_key
    assert consumer_key, 'outcome_service.consumer_key guaranteed to be non-null'

    try:
        consumer_secret = lti_provider.models.LtiConsumer.objects.get(key=consumer_key).secret
        assert consumer_secret, 'consumer secret guaranteed to be non-null'
    except ObjectDoesNotExist:
        log.error(
            "Outcome Service: Can't retrieve consumer secret for key %s.",
            consumer_key
        )
        return None

    # Calculate the OAuth signature for the replace_result message.
    # TODO: According to the LTI spec, there should be an additional
    # oauth_body_hash field that contains a digest of the replace_result
    # message. Testing with Canvas throws an error when this field is included.
    # This code may need to be revisited once we test with other LMS platforms,
    # and confirm whether there's a bug in Canvas.
    oauth = OAuth1(consumer_key, consumer_secret)

    headers = {'content-type': 'application/xml'}
    response = requests.post(
        assignment.outcome_service.lis_outcome_service_url,
        data=xml,
        auth=oauth,
        headers=headers
    )
    return response


def check_replace_result_response(response):
    if response.status_code != 200:
        log.error("Outcome service response: Unexpected status code {}".format(
            response.status_code
        ))
        return False

    # etree can't handle XML that declares character encoding. Strip off the
    # <?xml...?> tag and replace it with one that etree can parse
    xml = response.text
    if xml.lower().startswith('<?xml'):
        xml = '<?xml version="1.0"?>' + xml.split('?>', 1)[1]

    try:
        root = etree.fromstring(xml)
    except ParseError as e:
        log.error("Outcome service response: Failed to parse XML: %s", e)
        return False

    major_codes = root.xpath(
        '//ns:imsx_codeMajor',
        namespaces={'ns':'http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0'})
    if len(major_codes) != 1:
        log.error("Outcome service response: Expected exactly one imsx_codeMajor field in response.")
        return False

    if major_codes[0].text != 'success':
        log.error("Outcome service response: Unexpected major code: %s.", major_codes[0].text)
        return False
    return True
