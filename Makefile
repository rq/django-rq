test:
	 coverage run `which django-admin.py` test django_rq --settings=django_rq.tests.settings --pythonpath=.
	 python setup.py check --metadata --restructuredtext --strict
