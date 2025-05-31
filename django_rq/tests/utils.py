from django_rq.queues import get_connection, get_queue_by_index


def get_queue_index(name='default'):
    """
    Returns the position of Queue for the named queue in QUEUES_LIST
    """
    connection = get_connection(name)
    connection_kwargs = connection.connection_pool.connection_kwargs

    for i in range(0, 100):
        try:
            q = get_queue_by_index(i)
        except AttributeError:
            continue
        if q.name == name:
            # assert that the connection is correct
            assert q.connection.connection_pool.connection_kwargs == connection_kwargs

            return i

    return None
