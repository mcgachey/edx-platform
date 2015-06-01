"""
Database models for the LTI provider feature.

This app uses migrations. If you make changes to this model, be sure to create
an appropriate migration file and check it in at the same time as your model
changes. To do that,

1. Go to the edx-platform dir
2. ./manage.py lms schemamigration lti_provider --auto "description" --settings=devstack
"""
from django.contrib.auth.models import User
from django.db import models
import logging
from django.dispatch import receiver

from courseware.models import SCORE_CHANGED


from xmodule_django.models import CourseKeyField, UsageKeyField

log = logging.getLogger("edx.lti_provider")

# TODO: Move instance_guid into the LtiConsumer. Replace consumer_key and
# instance_guid in OutcomeService with foreign key into LtiConsumer. Move
# logic to index by GUID and then fall back on consumer key into LtiConsumer

class LtiConsumer(models.Model):
    """
    Database model representing an LTI consumer. This model stores the consumer
    specific settings, such as the OAuth key/secret pair and any LTI fields
    that must be persisted.
    """
    consumer_name = models.CharField(max_length=255)
    consumer_key = models.CharField(max_length=32, unique=True, db_index=True)
    consumer_secret = models.CharField(max_length=32, unique=True)


class OutcomeService(models.Model):
    """
    Model for a single outcome service associated with an LTI consumer. Note
    that a given consumer may have more than one outcome service URL over its
    lifetime, so we need to store the outcome service separately from the
    LtiConsumer model.

    An outcome service can be identified in two ways, depending on the
    information provided by an LTI launch. The ideal way to identify the service
    is by instance_guid, which should uniquely identify a consumer. However that
    field is optional in the LTI launch, and so if it is missing we can fall
    back on the consumer key (which should be created uniquely for each consumer
    although we don't have a technical way to guarantee that).

    Some LTI-specified fields use the prefix lis_; this refers to the IMS
    Learning Information Services standard from which LTI inherits some
    properties
    """
    lis_outcome_service_url = models.CharField(max_length=255)
    instance_guid = models.CharField(max_length=255, null=True)
    consumer_key = models.CharField(max_length=32, db_index=True)


class GradedAssignment(models.Model):
    """
    Model representing a single launch of a graded assignment by an individual
    user. There will be a row created here only if the LTI consumer may require
    a result to be returned from the LTI launch (determined by the presence of
    the lis_result_sourcedid parameter in the launch POST). There will be only
    one row created for a given user/course/usage/consumer combination; repeated
    launches of the same content by the same user from the same LTI consumer
    will not add new rows to the table.

    Some LTI-specified fields use the prefix lis_; this refers to the IMS
    Learning Information Services standard from which LTI inherits some
    properties
    """
    user = models.ForeignKey(User, db_index=True)
    course_key = CourseKeyField(max_length=255, db_index=True)
    usage_key = UsageKeyField(max_length=255, db_index=True)
    outcome_service = models.ForeignKey(OutcomeService)
    lis_result_sourcedid = models.CharField(max_length=255, db_index=True)

    class Meta:
        unique_together = ('outcome_service', 'lis_result_sourcedid')

import lti_provider.tasks

@receiver(SCORE_CHANGED)
def score_changed_handler(sender, **kwargs):  # pylint: disable=unused-argument
    """
    Consume signals that indicate score changes. See the definition of
    courseware.models.SCORE_CHANGED for a description of the signal.
    """
    points_possible = kwargs.get('points_possible', None)
    points_earned = kwargs.get('points_earned', None)
    user_id = kwargs.get('user_id', None)
    course_id = kwargs.get('course_id', None)
    usage_id = kwargs.get('usage_id', None)

    if None not in (points_earned, points_possible, user_id, course_id, user_id):
        lti_provider.tasks.send_outcome.delay(
            points_possible,
            points_earned,
            user_id,
            course_id,
            usage_id
        )
    else:
        log.error(
            "Outcome Service: Required signal parameter is None. "
            "points_possible: %s, points_earned: %s, user_id: %s, "
            "course_id: %s, usage_id: %s",
            points_possible, points_earned, user_id, course_id, usage_id
        )
