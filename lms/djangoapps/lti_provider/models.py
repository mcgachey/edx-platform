"""
Database models for the LTI provider feature.
"""
from django.contrib.auth.models import User
from django.db import models
from django.dispatch import receiver
import logging

from courseware.models import SCORE_CHANGED
import lti_provider.outcomes
from xmodule_django.models import CourseKeyField, UsageKeyField

log = logging.getLogger("edx.lti_provider")


class LtiConsumer(models.Model):
    """
    Database model representing an LTI consumer. This model stores the consumer
    specific settings, such as the OAuth key/secret pair and any LTI fields
    that must be persisted.
    """
    name = models.CharField(max_length=255, unique=True)
    key = models.CharField(max_length=32, unique=True, db_index=True)
    secret = models.CharField(max_length=32, unique=True)


class OutcomeService(models.Model):
    lis_outcome_service_url = models.CharField(max_length=256)
    instance_guid = models.CharField(max_length=256, null=True)
    consumer_key = models.CharField(max_length=32, db_index=True)


class GradedAssignment(models.Model):
    user = models.ForeignKey(User, db_index=True)
    course_key = CourseKeyField(max_length=255, db_index=True)
    usage_key = UsageKeyField(max_length=255, db_index=True)
    outcome_service = models.ForeignKey(OutcomeService)
    lis_result_sourcedid = models.CharField(max_length=255, db_index=True, unique=True)

    class Meta:
        unique_together = ('user', 'course_key', 'usage_key', 'outcome_service')


@receiver(SCORE_CHANGED)
def score_changed_handler(sender, **kwargs):  # pylint: disable=unused-argument
    """
    Consume signals that indicate score changes.
    """
    points_possible = kwargs.get('points_possible', None)
    points_earned = kwargs.get('points_earned', None)
    user_id = kwargs.get('user_id', None)
    course_id = kwargs.get('course_id', None)
    usage_id = kwargs.get('usage_id', None)

    if all((points_possible, points_earned, user_id, course_id, user_id)):
        lti_provider.outcomes.send_outcome(
            points_possible,
            points_earned,
            user_id,
            course_id,
            usage_id
        )
    else:
        log.error(
            "Outcome Service: Required signal parameter is None. points_possible: %s, "
            "points_earned: %s, user_id: %s, course_id: %s, usage_id: %s",
            points_possible, points_earned, user_id, course_id, usage_id
        )
