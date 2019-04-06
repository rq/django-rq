from django_rq.queues import get_connection, get_queue_by_index


def get_queue_index(name='default'):
    """
    Returns the position of Queue for the named queue in QUEUES_LIST
    """
    queue_index = None
    connection = get_connection(name)
    connection_kwargs = connection.connection_pool.connection_kwargs
    for i in range(0, 100):
        q = get_queue_by_index(i)
        if q.name == name and q.connection.connection_pool.connection_kwargs == connection_kwargs:
            queue_index = i
            break
    return queue_index
