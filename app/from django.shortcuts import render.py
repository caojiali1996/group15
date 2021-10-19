from django.shortcuts import render
from django.db import connections
from django.shortcuts import redirect
from django.http import Http404
from django.db.utils import IntegrityError



with connections['default'].cursor() as cursor:
    cursor.execute(f'''
        SELECT ship_type,
        CAST(AVG(technical_efficiency_number)AS decimal(10,2)) AS ave
        FROM co2emission_reduced
        GROUP BY ship_type
        ''')
    result = cursor.fetchall()
print(result)