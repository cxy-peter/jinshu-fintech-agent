from contextvars import ContextVar
scope=ContextVar('scope',default=None)
run_state=ContextVar('run_state',default=None)

access=ContextVar('access',default=None)
