from django.db import models
from django.core.exceptions import ValidationError


class Station(models.Model):
    code = models.CharField(max_length=20, unique=True, verbose_name='驿站编号')
    name = models.CharField(max_length=100, verbose_name='驿站名称')
    latitude = models.FloatField(verbose_name='纬度')
    longitude = models.FloatField(verbose_name='经度')
    description = models.TextField(blank=True, default='', verbose_name='描述')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '驿站'
        verbose_name_plural = '驿站'
        ordering = ['code']

    def __str__(self):
        return f'{self.code} - {self.name}'

    def clean(self):
        super().clean()
        if Station.objects.filter(code=self.code).exclude(pk=self.pk).exists():
            raise ValidationError({'code': '驿站编号不能重复'})


class Road(models.Model):
    GRADE_CHOICES = [
        (1, '官道（最优）'),
        (2, '驿道（良好）'),
        (3, '乡道（一般）'),
        (4, '山路（较差）'),
        (5, '险道（极差）'),
    ]
    from_station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name='roads_from', verbose_name='起点驿站')
    to_station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name='roads_to', verbose_name='终点驿站')
    distance = models.FloatField(verbose_name='道路长度（里）')
    slope = models.FloatField(default=0, verbose_name='坡度（度）')
    grade = models.IntegerField(choices=GRADE_CHOICES, default=2, verbose_name='通行等级')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '道路'
        verbose_name_plural = '道路'
        unique_together = ['from_station', 'to_station']

    def __str__(self):
        return f'{self.from_station.code} → {self.to_station.code} ({self.distance}里)'

    def clean(self):
        super().clean()
        if self.distance is not None and self.distance <= 0:
            raise ValidationError({'distance': '道路长度必须大于0'})
        if self.from_station_id and self.to_station_id and self.from_station_id == self.to_station_id:
            raise ValidationError('起点和终点不能相同')


class HorseChangeStrategy(models.Model):
    name = models.CharField(max_length=100, verbose_name='策略名称')
    interval_distance = models.FloatField(verbose_name='换马间隔（里）')
    change_time = models.FloatField(default=0.5, verbose_name='换马耗时（时辰）')
    description = models.TextField(blank=True, default='', verbose_name='描述')

    class Meta:
        verbose_name = '换马策略'
        verbose_name_plural = '换马策略'

    def __str__(self):
        return f'{self.name} (每{self.interval_distance}里换马)'

    def clean(self):
        super().clean()
        if self.interval_distance is not None and self.interval_distance < 0:
            raise ValidationError({'interval_distance': '换马间隔不能为负数'})


class WeatherRecord(models.Model):
    WEATHER_CHOICES = [
        (1, '晴朗'),
        (2, '多云'),
        (3, '小雨'),
        (4, '大雨'),
        (5, '暴雨'),
        (6, '小雪'),
        (7, '大雪'),
        (8, '暴雪'),
    ]
    SEVERITY_MAP = {
        1: 1.0, 2: 1.1, 3: 1.3, 4: 1.6,
        5: 2.0, 6: 1.4, 7: 1.8, 8: 2.5,
    }
    road = models.ForeignKey(Road, on_delete=models.CASCADE, related_name='weather_records', verbose_name='道路')
    weather_type = models.IntegerField(choices=WEATHER_CHOICES, default=1, verbose_name='天气类型')
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '天气记录'
        verbose_name_plural = '天气记录'
        ordering = ['-recorded_at']

    def __str__(self):
        return f'{self.road} - {self.get_weather_type_display()}'

    @property
    def speed_factor(self):
        return self.SEVERITY_MAP.get(self.weather_type, 1.0)


class DeliveryTask(models.Model):
    STATUS_CHOICES = [
        ('draft', '草稿'),
        ('executable', '可执行'),
        ('in_progress', '执行中'),
        ('completed', '已完成'),
        ('delayed', '已延误'),
    ]
    PRIORITY_CHOICES = [
        (1, '普通'),
        (2, '加急'),
        (3, '八百里加急'),
    ]
    task_code = models.CharField(max_length=50, unique=True, verbose_name='任务编号')
    origin = models.ForeignKey(Station, on_delete=models.CASCADE, related_name='tasks_from', verbose_name='起点驿站')
    destination = models.ForeignKey(Station, on_delete=models.CASCADE, related_name='tasks_to', verbose_name='终点驿站')
    strategy = models.ForeignKey(HorseChangeStrategy, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='换马策略')
    priority = models.IntegerField(choices=PRIORITY_CHOICES, default=1, verbose_name='优先级')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name='状态')
    estimated_hours = models.FloatField(null=True, blank=True, verbose_name='预计送达（时辰）')
    actual_hours = models.FloatField(null=True, blank=True, verbose_name='实际送达（时辰）')
    has_high_risk = models.BooleanField(default=False, verbose_name='存在高风险断点')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '递送任务'
        verbose_name_plural = '递送任务'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.task_code}: {self.origin.code} → {self.destination.code}'

    def clean(self):
        super().clean()
        if self.origin_id and self.destination_id and self.origin_id == self.destination_id:
            raise ValidationError('起点和终点不能相同')


class DeliverySegment(models.Model):
    task = models.ForeignKey(DeliveryTask, on_delete=models.CASCADE, related_name='segments', verbose_name='递送任务')
    road = models.ForeignKey(Road, on_delete=models.CASCADE, verbose_name='道路段')
    order = models.IntegerField(verbose_name='顺序')
    segment_time = models.FloatField(null=True, blank=True, verbose_name='本段用时（时辰）')
    is_high_risk = models.BooleanField(default=False, verbose_name='高风险段')

    class Meta:
        verbose_name = '递送段'
        verbose_name_plural = '递送段'
        ordering = ['task', 'order']

    def __str__(self):
        return f'{self.task.task_code} - 第{self.order}段'
