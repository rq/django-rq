from django_rq.queues import get_connection, get_queue_by_index


def get_queue_index(name='default'):
    """
    Returns the position of Queue for the named queue in QUEUES_LIST
    """
    connection = get_connection(name)
    connection_kwargs = dict(connection.connection_pool.connection_kwargs)

    special_case_retry = False
    if (retry := connection_kwargs.get('retry')) and retry.__class__.__eq__ == object.__eq__:
        special_case_retry = True
        del connection_kwargs['retry']

    for i in range(0, 100):
        try:
            q = get_queue_by_index(i)
        except AttributeError:
            continue
        if q.name == name:
            # assert that the connection is correct
            if special_case_retry:
                q_connection_kwargs = dict(q.connection.connection_pool.connection_kwargs)
                q_retry = q_connection_kwargs.pop('retry', None)
                assert q_connection_kwargs == q_connection_kwargs
                assert retry  # for mypy
                assert (
                    q_retry.__class__ == retry.__class__
                    and q_retry._retries == retry._retries
                    and set(q_retry._supported_errors) == set(retry._supported_errors)
                    and q_retry._backoff.__class__ == retry._backoff.__class__
                    and q_retry._backoff.__dict__ == retry._backoff.__dict__
                )
            else:
                assert q.connection.connection_pool.connection_kwargs == connection_kwargs

            return i

    return None
