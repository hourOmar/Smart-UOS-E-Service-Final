class AgentError(Exception):
    """An error the agent raises deliberately; its message is safe to show to staff."""


class RequestNotFoundError(AgentError):
    pass


class NotRaiseCapacityRequestError(AgentError):
    pass


class StudentNotFoundError(AgentError):
    pass


class CourseNotFoundError(AgentError):
    pass


class SectionNotFoundError(AgentError):
    pass


class SectionCourseMismatchError(AgentError):
    pass


class EligibilityReplyInvalidError(AgentError):
    """Every Gemini reply was unusable (unparsable, or its recommendation
    contradicted the policy for the verified evidence). The run fails; no
    recommendation is produced."""
