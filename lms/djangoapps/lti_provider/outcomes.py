"""
Helper functions for managing interactions with the LTI outcomes service defined
in LTI v1.1.
"""

from django.core.exceptions import ObjectDoesNotExist
import logging
from lxml import etree
import requests
import requests_oauthlib
import uuid

from lti_provider.models import GradedAssignment, LtiConsumer, OutcomeService

log = logging.getLogger("edx.lti_provider")


def store_outcome_parameters(request_params, user):
    """
    Determine whether a set of LTI launch parameters contains information about
    an expected score, and if so create a GradedAssignment record. Create a new
    OutcomeService record if none exists for the tool consumer, and update any
    incomplete record with additional data if it is available.
    """
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
                "Request parameters: %s",
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
        assert None not in [usage_key, course_key], "usage_key ({}) and course_key ({}) should not be None".format(
            usage_key, course_key
        )

        # Create a record of the outcome service if necessary
        outcomes, __ = OutcomeService.objects.get_or_create(
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
        GradedAssignment.objects.get_or_create(
            lis_result_sourcedid=result_id,
            course_key=course_key,
            usage_key=usage_key,
            user=user,
            outcome_service=outcomes
        )


# Pylint doesn't recognize members in the LXML module
# pylint: disable=no-member
def generate_replace_result_xml(result_sourcedid, score):
    """
    Create the XML document that contains the new score to be sent to the LTI
    consumer. The format of this message is defined in the LTI 1.1 spec.
    """
    envelope = etree.Element(
        'imsx_POXEnvelopeRequest',
        xmlns='http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0'
    )
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
    """
    Take the XML document generated in generate_replace_result_xml, and sign it
    with the consumer key and secret assigned to the consumer. Send the signed
    message to the LTI consumer.
    """
    outcome_service = assignment.outcome_service
    assert outcome_service, 'assignment.outcome_service guaranteed to be non-null'
    consumer_key = outcome_service.consumer_key
    assert consumer_key, 'outcome_service.consumer_key guaranteed to be non-null'

    # Fetch the secret associated with the consumer key
    try:
        consumer_secret = LtiConsumer.objects.get(
            consumer_key=consumer_key
        ).consumer_secret
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
    oauth = requests_oauthlib.OAuth1(consumer_key, consumer_secret)

    headers = {'content-type': 'application/xml'}
    response = requests.post(
        assignment.outcome_service.lis_outcome_service_url,
        data=xml,
        auth=oauth,
        headers=headers
    )
    return response


def check_replace_result_response(response):
    """
    Parse the response sent by the LTI consumer after an score update message
    has been processed. Return True if the message was properly received, or
    False if not. The format of this message is defined in the LTI 1.1 spec.
    """
    if response.status_code != 200:
        log.error(
            "Outcome service response: Unexpected status code %s",
            response.status_code
        )
        return False

    # etree can't handle XML that declares character encoding. Strip off the
    # <?xml...?> tag and replace it with one that etree can parse
    xml = response.text
    if xml.lower().startswith('<?xml'):
        xml = '<?xml version="1.0"?>' + xml.split('?>', 1)[1]

    try:
        root = etree.fromstring(xml)
    except etree.ParseError as ex:
        log.error("Outcome service response: Failed to parse XML: %s", ex)
        return False

    major_codes = root.xpath(
        '//ns:imsx_codeMajor',
        namespaces={'ns': 'http://www.imsglobal.org/services/ltiv1p1/xsd/imsoms_v1p0'})
    if len(major_codes) != 1:
        log.error("Outcome service response: Expected exactly one imsx_codeMajor field in response.")
        return False

    if major_codes[0].text != 'success':
        log.error("Outcome service response: Unexpected major code: %s.", major_codes[0].text)
        return False
    return True
