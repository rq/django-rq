test:
	 coverage run `which django-admin.py` test tests --settings=tests.settings --pythonpath=.
	 python setup.py check --metadata --strict
