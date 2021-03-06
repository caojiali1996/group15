from django.shortcuts import render
from django.db import connections
from django.shortcuts import redirect
from django.http import Http404
from django.db.utils import IntegrityError


from app.utils import namedtuplefetchall, clamp
from app.forms import ImoForm

PAGE_SIZE = 20
COLUMNS = [
    'imo',
    'ship_name',
    'technical_efficiency_number',
    'ship_type',
    'issue_date',
    'expiry_date'
]


def index(request):
    """Shows the main page"""
    context = {'nbar': 'home'}
    return render(request, 'index.html', context)


def db(request):
    """Shows very simple DB page"""
    with connections['default'].cursor() as cursor:
        cursor.execute('INSERT INTO app_greeting ("when") VALUES (NOW());')
        cursor.execute('SELECT "when" FROM app_greeting;')
        greetings = namedtuplefetchall(cursor)

    context = {'greetings': greetings, 'nbar': 'db'}
    return render(request, 'db.html', context)


def emissions(request, page=1):
    """Shows the emissions table page"""
    msg = None
    order_by = request.GET.get('order_by', '')
    order_by = order_by if order_by in COLUMNS else 'imo'

    with connections['default'].cursor() as cursor:
        cursor.execute('SELECT COUNT(*) FROM co2emission_reduced')
        count = cursor.fetchone()[0]
        num_pages = (count - 1) // PAGE_SIZE + 1
        page = clamp(page, 1, num_pages)

        offset = (page - 1) * PAGE_SIZE
        cursor.execute(f'''
            SELECT {", ".join(COLUMNS)}
            FROM co2emission_reduced
            ORDER BY {order_by}
            OFFSET %s
            LIMIT %s
        ''', [offset, PAGE_SIZE])
        rows = namedtuplefetchall(cursor)

    imo_deleted = request.GET.get('deleted', False)
    if imo_deleted:
        msg = f'✔ IMO {imo_deleted} deleted'

    context = {
        'nbar': 'emissions',
        'page': page,
        'rows': rows,
        'num_pages': num_pages,
        'msg': msg,
        'order_by': order_by
    }
    return render(request, 'emissions.html', context)


def aggregation(request, page=1):
    """Shows the aggregation table page"""
    agg = ['country','month','ship_type']
    order_by = request.GET.get('order_by', '')
    order_by = order_by if order_by in agg else 'country'

    with connections['default'].cursor() as cursor:
        cursor.execute('SELECT COUNT(*) FROM co2emission_reduced')
        count = 450
        num_pages = (count - 1) // PAGE_SIZE + 1
        page = clamp(page, 1, num_pages)

        offset = (page - 1) * PAGE_SIZE
        cursor.execute(f'''
            select v.country, d.month, s.ship_type, count(f.ship) as count, max(f.eedi) as max_eedi, min(f.eedi) as min_eedi, max(f.eiv) as max_eiv, min(f.eiv) as min_eiv, sum(total_co2_emissions) as sum_co2, sum(total_fuel_consumption) as sum_fuel
            from date d, fact f, ships s, verifiers v
            where f.ship = s.id
            and f.issue_date = d.id
            and f.verifier = v.id
            group by rollup(v.country, d.month, s.ship_type)
            ORDER BY {order_by}
            OFFSET %s
            LIMIT %s
            ''',[offset, PAGE_SIZE])
        rows = namedtuplefetchall(cursor)
    context = {
        'nbar': 'aggregation',
        'page': page,
        'rows': rows,
        'num_pages': num_pages,
        'order_by': order_by
    }
    return render(request, 'aggregation.html', context)

def visual(request):
    """Shows the visual page"""
    with connections['default'].cursor() as cursor:
        cursor.execute(f'''
        select  v.country, 
                avg(f.totol_time_spent_at_sea) as Avg_time_spent, 
                avg(f.total_co2_emissions) as Avg_CO2_emissions
        from fact f left join ships s on f.ship=s.id left join verifiers v on f.verifier=v.id
        group by v.country
        order by v.country
            ''')
        res1 = list(cursor.fetchall())
        labels1 = list([item[0] for item in res1])
        avg_time = list([item[1] for item in res1])
        avg_emi = list([item[2] for item in res1])
        
        cursor.execute(f'''
            select s.ship_type, sum(f.total_co2_emissions)
            from fact f left join ships s on f.ship=s.id
            group by s.ship_type
            order by sum(f.total_co2_emissions) desc
            ''')
        res2 = list(cursor.fetchall())
        labels2 = list([item[0] for item in res2])
        sum2 = list([item[1] for item in res2])
     
    context = {
        'nbar': 'visual',
        'labels1':labels1,
        'labels2':labels2,
        'sum2': sum2,
        'avg_time':avg_time,
        'avg_emi':avg_emi
    }
    return render(request, 'visual.html', context)

def radarchart(request):
    """Shows the radar page"""
    with connections['default'].cursor() as cursor:
        cursor.execute(f'''
            select v.country, max(f.eiv) as max_eiv, min(f.eiv) as min_eiv
            from fact f, verifiers v
            where f.verifier = v.id
            and v.country<>'Portugal'
            group by v.country
            ''')
        res3 = namedtuplefetchall(cursor)
        labels3 = [getattr(i, 'country') for i in res3]
        max_eiv = [float(getattr(i, 'max_eiv')**0.5) for i in res3]
        min_eiv = [float(getattr(i, 'min_eiv')**0.5) for i in res3]
    context = {
        'labels3':labels3,
        'max_eiv': max_eiv,
        'min_eiv': min_eiv
    }
    return render(request, 'radarchart.html', context)
    

def insert_update_values(form, post, action, imo):
    """
    Inserts or updates database based on values in form and action to take,
    and returns a tuple of whether action succeded and a message.
    """
    if not form.is_valid():
        return False, 'There were errors in your form'

    # Set values to None if left blank
    cols = COLUMNS[:]
    values = [post.get(col, None) for col in cols]
    values = [val if val != '' else None for val in values]

    if action == 'update':
        # Remove imo from updated fields
        cols, values = cols[1:], values[1:]
        with connections['default'].cursor() as cursor:
            cursor.execute(f'''
                UPDATE co2emission_reduced
                SET {", ".join(f"{col} = %s" for col in cols)}
                WHERE imo = %s;
            ''', [*values, imo])
        return True, '✔ IMO updated successfully'

    # Else insert
    with connections['default'].cursor() as cursor:
        cursor.execute(f'''
            INSERT INTO co2emission_reduced ({", ".join(cols)})
            VALUES ({", ".join(["%s"] * len(cols))});
        ''', values)
    return True, '✔ IMO inserted successfully'


def emission_detail(request, imo=None):
    """Shows the form where the user can insert or update an IMO"""
    success, form, msg, initial_values = False, None, None, {}
    is_update = imo is not None

    if is_update and request.GET.get('inserted', False):
        success, msg = True, f'✔ IMO {imo} inserted'

    if request.method == 'POST':
        # Since we set imo=disabled for updating, the value is not in the POST
        # data so we need to set it manually. Otherwise if we are doing an
        # insert, it will be None but filled out in the form
        if imo:
            request.POST._mutable = True
            request.POST['imo'] = imo
        else:
            imo = request.POST['imo']

        form = ImoForm(request.POST)
        action = request.POST.get('action', None)

        if action == 'delete':
            with connections['default'].cursor() as cursor:
                cursor.execute('DELETE FROM co2emission_reduced WHERE imo = %s;', [imo])
            return redirect(f'/emissions?deleted={imo}')
        try:
            success, msg = insert_update_values(form, request.POST, action, imo)
            if success and action == 'insert':
                return redirect(f'/emissions/imo/{imo}?inserted=true')
        except IntegrityError:
            success, msg = False, 'IMO already exists'
        except Exception as e:
            success, msg = False, f'Some unhandled error occured: {e}'
    elif imo:  # GET request and imo is set
        with connections['default'].cursor() as cursor:
            cursor.execute('SELECT * FROM co2emission_reduced WHERE imo = %s', [imo])
            try:
                initial_values = namedtuplefetchall(cursor)[0]._asdict()
            except IndexError:
                raise Http404(f'IMO {imo} not found')

    # Set dates (if present) to iso format, necessary for form
    # We don't use this in class, but you will need it for your project
    for field in ['doc_issue_date', 'doc_expiry_date']:
        if initial_values.get(field, None) is not None:
            initial_values[field] = initial_values[field].isoformat()

    # Initialize form if not done already
    form = form or ImoForm(initial=initial_values)
    if is_update:
        form['imo'].disabled = True

    context = {
        'nbar': 'emissions',
        'is_update': is_update,
        'imo': imo,
        'form': form,
        'msg': msg,
        'success': success
    }
    return render(request, 'emission_detail.html', context)
