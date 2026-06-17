import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'relay.settings')
django.setup()
from courier.models import Station, Road, HorseChangeStrategy, DeliveryTask
from courier.engine import calculate_delivery_time, find_path

stations = list(Station.objects.order_by('pk'))
print(f'驿站数: {len(stations)}')
print(f'道路数: {Road.objects.count()}')

task = None
for s1 in stations:
    for s2 in stations:
        if s1.pk != s2.pk:
            path = find_path(s1.pk, s2.pk)
            if path:
                print(f'找到连通路线: {s1.code} -> {s2.code}, 路段数: {len(path)}')
                strategy = HorseChangeStrategy.objects.first()
                try:
                    task = DeliveryTask.objects.get(task_code='DEMO-001')
                    task.origin = s1
                    task.destination = s2
                    task.strategy = strategy
                    task.priority = 2
                    task.deadline_hours = 3.0
                    task.departure_offset = 0.5
                    task.save()
                except DeliveryTask.DoesNotExist:
                    task = DeliveryTask.objects.create(
                        task_code='DEMO-001',
                        origin=s1,
                        destination=s2,
                        strategy=strategy,
                        priority=2,
                        deadline_hours=3.0,
                        departure_offset=0.5,
                    )
                calculate_delivery_time(task, force_recalculate=True)
                print(f'任务 {task.task_code} 已创建/更新')
                print(f'  预计送达: {task.estimated_hours} 时辰')
                print(f'  延误预警: {task.delay_warning}')
                print(f'  高风险: {task.has_high_risk}')
                print(f'  方案数: {task.plans.count()}')
                break
    if task:
        break

if not task:
    print('未找到连通路线')
