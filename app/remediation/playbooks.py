PLAYBOOKS = {}

def register_playbook(name):
    def decorator(fn):
        PLAYBOOKS[name] = fn
        return fn
    return decorator
