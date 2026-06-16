import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'relay.settings')
django.setup()

from courier.models import Station, Road, HorseChangeStrategy, WeatherRecord

if Station.objects.count() == 0:
    stations_data = [
        ('YZ001', '长安驿', 34.26, 108.94, '京畿首驿，西出第一站'),
        ('YZ002', '灞桥驿', 34.37, 109.07, '灞桥折柳处'),
        ('YZ003', '渭南驿', 34.50, 109.50, '渭水之南'),
        ('YZ004', '华阴驿', 34.57, 110.09, '华山脚下'),
        ('YZ005', '潼关驿', 34.54, 110.24, '潼关天险'),
        ('YZ006', '函谷驿', 34.64, 110.54, '函谷关前'),
        ('YZ007', '陕州驿', 34.77, 111.20, '陕州古城'),
        ('YZ008', '洛阳驿', 34.68, 112.45, '东都洛阳'),
    ]
    for code, name, lat, lng, desc in stations_data:
        Station.objects.create(code=code, name=name, latitude=lat, longitude=lng, description=desc)
    print(f'已创建 {len(stations_data)} 个驿站')

if Road.objects.count() == 0:
    stations = list(Station.objects.all().order_by('code'))
    roads_data = [
        (0, 1, 30, 2, 1),
        (1, 2, 50, 5, 2),
        (2, 3, 60, 8, 2),
        (3, 4, 40, 12, 3),
        (4, 5, 35, 15, 4),
        (5, 6, 70, 3, 2),
        (6, 7, 100, 5, 1),
    ]
    for from_idx, to_idx, dist, slope, grade in roads_data:
        Road.objects.create(
            from_station=stations[from_idx],
            to_station=stations[to_idx],
            distance=dist,
            slope=slope,
            grade=grade,
        )
    print(f'已创建 {len(roads_data)} 条道路')

if HorseChangeStrategy.objects.count() == 0:
    strategies_data = [
        ('快速换马', 30, 0.3, '每30里换马，适合加急文书'),
        ('标准换马', 50, 0.5, '每50里换马，常规递送'),
        ('长途缓行', 80, 0.8, '每80里换马，节省换马时间'),
    ]
    for name, interval, change_time, desc in strategies_data:
        HorseChangeStrategy.objects.create(name=name, interval_distance=interval, change_time=change_time, description=desc)
    print(f'已创建 {len(strategies_data)} 种换马策略')

if WeatherRecord.objects.count() == 0:
    roads = Road.objects.all()
    for road in roads:
        WeatherRecord.objects.create(road=road, weather_type=1)
    print(f'已为 {roads.count()} 条道路创建默认天气记录')
