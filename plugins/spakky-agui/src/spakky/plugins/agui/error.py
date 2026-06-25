"""Error classes for the spakky-agui plugin."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractAgUiError(AbstractSpakkyFrameworkError, ABC):
    """Base class for AG-UI adapter errors."""

    ...


class AgUiApprovalDecodeError(AbstractAgUiError):
    """Raised when a resume input claims an approval decision it cannot supply.

    The AG-UI resume carries an approval decision either as a tool-result
    message addressed to the deferred ``hitl_approval`` call or as a
    ``forwardedProps.approvalDecision`` object. This error is raised when that
    payload is present but malformed: the request id is missing, the decision
    string is absent, or the decision is not a member of ``ApprovalDecision``.
    """

    message = "AG-UI approval decision payload is missing or invalid"


class AgUiPendingApprovalError(AbstractAgUiError):
    """Raised when a paused-for-approval state carries malformed approval metadata.

    After ``run_events`` ends, the transport reads the durable WAIT_FOR_APPROVAL
    state to surface the deferred-tool approval request. The runner stores the
    ``AgentApprovalRequest`` under ``metadata["approval"]`` with the prompt in
    ``current_activity``; this error is raised when a state flagged
    ``APPROVAL_REQUIRED`` is missing that metadata, omits the prompt, or carries
    an unknown decision — an impossible state the adapter refuses to paper over.
    """

    message = "AG-UI pending approval state is missing or has invalid metadata"


class AgUiRunResolutionError(AbstractAgUiError):
    """Raised when an SSE request references a run the driver cannot resolve.

    The endpoint maps an AG-UI ``RunAgentInput`` to a core run, then asks the
    run-driver factory to build a driver for it. This error is raised when the
    factory cannot produce a runner for the requested agent/run — for example,
    the AG-UI input omits the last user message the core run requires to seed a
    model request.
    """

    message = "AG-UI run request could not be resolved to a runnable agent run"
