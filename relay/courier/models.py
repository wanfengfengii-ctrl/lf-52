from django.db import models
from django.core.exceptions import ValidationError


class Station(models.Model):
    QUEUE_RULE_CHOICES = [
        ('fifo', '先进先出（无插队）'),
        ('priority_strict', '严格优先级（高优先级完全优先）'),
        ('priority_weighted', '加权优先级（高优先级概率插队）'),
        ('priority_class', '优先级分类（同级内先进先出）'),
    ]

    code = models.CharField(max_length=20, unique=True, verbose_name='驿站编号')
    name = models.CharField(max_length=100, verbose_name='驿站名称')
    latitude = models.FloatField(verbose_name='纬度')
    longitude = models.FloatField(verbose_name='经度')
    capacity = models.IntegerField(default=5, verbose_name='同时处理任务数')
    window_count = models.IntegerField(default=1, verbose_name='处理窗口数量')
    process_time = models.FloatField(default=0.2, verbose_name='中转处理耗时（时辰）')
    queue_rule = models.CharField(
        max_length=20,
        choices=QUEUE_RULE_CHOICES,
        default='priority_class',
        verbose_name='排队插队规则'
    )
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
        if self.capacity is not None and self.capacity < 1:
            raise ValidationError({'capacity': '驿站处理能力至少为1'})
        if self.window_count is not None and self.window_count < 1:
            raise ValidationError({'window_count': '处理窗口数量至少为1'})
        if self.process_time is not None and self.process_time < 0:
            raise ValidationError({'process_time': '中转处理耗时不能为负数'})


class StationPeakHour(models.Model):
    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name='peak_hours', verbose_name='驿站')
    start_hour = models.FloatField(verbose_name='开始时间（时辰，0-24）')
    end_hour = models.FloatField(verbose_name='结束时间（时辰，0-24）')
    capacity_multiplier = models.FloatField(default=0.6, verbose_name='处理能力倍率')
    arrival_multiplier = models.FloatField(default=1.8, verbose_name='到达率倍率')
    process_delay_pct = models.FloatField(default=30, verbose_name='处理时延增幅（%）')
    label = models.CharField(max_length=50, blank=True, default='', verbose_name='时段标签')

    class Meta:
        verbose_name = '驿站高峰时段'
        verbose_name_plural = '驿站高峰时段'
        ordering = ['station', 'start_hour']

    def __str__(self):
        label = self.label or f'{self.start_hour}-{self.end_hour}时'
        return f'{self.station.code} - {label}'

    def clean(self):
        super().clean()
        if self.start_hour < 0 or self.start_hour >= 24:
            raise ValidationError({'start_hour': '开始时间必须在 0-24 时辰之间'})
        if self.end_hour <= 0 or self.end_hour > 24:
            raise ValidationError({'end_hour': '结束时间必须在 0-24 时辰之间'})
        if self.start_hour >= self.end_hour:
            raise ValidationError('开始时间必须早于结束时间')
        if self.capacity_multiplier <= 0:
            raise ValidationError({'capacity_multiplier': '处理能力倍率必须大于0'})
        if self.arrival_multiplier <= 0:
            raise ValidationError({'arrival_multiplier': '到达率倍率必须大于0'})


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
    PLAN_TYPE_CHOICES = [
        ('fastest', '最短送达'),
        ('safest', '最稳妥方案'),
        ('balanced', '均衡方案'),
    ]
    task_code = models.CharField(max_length=50, unique=True, verbose_name='任务编号')
    origin = models.ForeignKey(Station, on_delete=models.CASCADE, related_name='tasks_from', verbose_name='起点驿站')
    destination = models.ForeignKey(Station, on_delete=models.CASCADE, related_name='tasks_to', verbose_name='终点驿站')
    strategy = models.ForeignKey(HorseChangeStrategy, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='换马策略')
    priority = models.IntegerField(choices=PRIORITY_CHOICES, default=1, verbose_name='优先级')
    deadline_hours = models.FloatField(null=True, blank=True, verbose_name='要求时限（时辰）')
    departure_offset = models.FloatField(default=0.0, verbose_name='出发时间偏移（时辰）')
    selected_plan_type = models.CharField(max_length=20, choices=PLAN_TYPE_CHOICES, default='fastest', verbose_name='选用方案类型')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name='状态')
    estimated_hours = models.FloatField(null=True, blank=True, verbose_name='预计送达（时辰）')
    actual_hours = models.FloatField(null=True, blank=True, verbose_name='实际送达（时辰）')
    has_high_risk = models.BooleanField(default=False, verbose_name='存在高风险断点')
    delay_warning = models.BooleanField(default=False, verbose_name='延误预警')
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
        if self.deadline_hours is not None and self.deadline_hours <= 0:
            raise ValidationError({'deadline_hours': '要求时限必须大于0'})
        if self.departure_offset is not None and self.departure_offset < 0:
            raise ValidationError({'departure_offset': '出发时间偏移不能为负数'})


class DeliverySegment(models.Model):
    task = models.ForeignKey(DeliveryTask, on_delete=models.CASCADE, related_name='segments', verbose_name='递送任务')
    road = models.ForeignKey(Road, on_delete=models.CASCADE, verbose_name='道路段')
    order = models.IntegerField(verbose_name='顺序')
    segment_time = models.FloatField(null=True, blank=True, verbose_name='本段用时（时辰）')
    travel_time = models.FloatField(null=True, blank=True, verbose_name='行进时间（时辰）')
    horse_change_time = models.FloatField(null=True, blank=True, verbose_name='换马时间（时辰）')
    process_time = models.FloatField(default=0.0, verbose_name='中转处理时间（时辰）')
    is_high_risk = models.BooleanField(default=False, verbose_name='高风险段')
    override_strategy = models.ForeignKey(HorseChangeStrategy, on_delete=models.SET_NULL, null=True, blank=True, related_name='override_segments', verbose_name='本段独立换马策略')
    override_weather = models.IntegerField(choices=WeatherRecord.WEATHER_CHOICES, null=True, blank=True, verbose_name='本段独立天气')
    departure_time = models.FloatField(null=True, blank=True, verbose_name='本段出发时间（时辰）')
    arrival_time = models.FloatField(null=True, blank=True, verbose_name='本段到达时间（时辰）')

    class Meta:
        verbose_name = '递送段'
        verbose_name_plural = '递送段'
        ordering = ['task', 'order']

    def __str__(self):
        return f'{self.task.task_code} - 第{self.order}段'


class DeliveryPlan(models.Model):
    PLAN_TYPE_CHOICES = [
        ('fastest', '最短送达方案'),
        ('safest', '最稳妥方案'),
        ('balanced', '均衡方案'),
        ('alternative', '备选方案'),
    ]
    task = models.ForeignKey(DeliveryTask, on_delete=models.CASCADE, related_name='plans', verbose_name='递送任务')
    plan_type = models.CharField(max_length=20, choices=PLAN_TYPE_CHOICES, verbose_name='方案类型')
    total_time = models.FloatField(verbose_name='总耗时（时辰）')
    total_distance = models.FloatField(default=0.0, verbose_name='总距离（里）')
    risk_count = models.IntegerField(default=0, verbose_name='高风险段数')
    station_count = models.IntegerField(default=0, verbose_name='途经驿站数')
    is_delay_risk = models.BooleanField(default=False, verbose_name='存在延误风险')
    delay_probability = models.FloatField(default=0.0, verbose_name='延误概率')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '递送方案'
        verbose_name_plural = '递送方案'
        ordering = ['task', 'plan_type']

    def __str__(self):
        return f'{self.task.task_code} - {self.get_plan_type_display()}'


class PlanSegment(models.Model):
    plan = models.ForeignKey(DeliveryPlan, on_delete=models.CASCADE, related_name='segments', verbose_name='递送方案')
    road = models.ForeignKey(Road, on_delete=models.CASCADE, verbose_name='道路段')
    order = models.IntegerField(verbose_name='顺序')
    segment_time = models.FloatField(verbose_name='本段用时（时辰）')
    travel_time = models.FloatField(default=0.0, verbose_name='行进时间（时辰）')
    horse_change_time = models.FloatField(default=0.0, verbose_name='换马时间（时辰）')
    process_time = models.FloatField(default=0.0, verbose_name='中转处理时间（时辰）')
    is_high_risk = models.BooleanField(default=False, verbose_name='高风险段')
    departure_time = models.FloatField(null=True, blank=True, verbose_name='本段出发时间（时辰）')
    arrival_time = models.FloatField(null=True, blank=True, verbose_name='本段到达时间（时辰）')
    strategy_name = models.CharField(max_length=100, blank=True, default='', verbose_name='换马策略名称')
    weather_display = models.CharField(max_length=50, blank=True, default='', verbose_name='天气状况')

    class Meta:
        verbose_name = '方案路段'
        verbose_name_plural = '方案路段'
        ordering = ['plan', 'order']


class SimulationRun(models.Model):
    STATUS_CHOICES = [
        ('pending', '待运行'),
        ('running', '运行中'),
        ('completed', '已完成'),
        ('failed', '运行失败'),
    ]

    name = models.CharField(max_length=200, verbose_name='仿真名称')
    description = models.TextField(blank=True, default='', verbose_name='描述')
    sim_start_time = models.FloatField(default=0.0, verbose_name='仿真起始时间（时辰）')
    sim_end_time = models.FloatField(default=24.0, verbose_name='仿真结束时间（时辰）')
    random_seed = models.IntegerField(default=42, verbose_name='随机种子')
    task_count = models.IntegerField(default=50, verbose_name='任务数量')
    enable_peak_hours = models.BooleanField(default=True, verbose_name='启用高峰时段')
    priority_distribution = models.JSONField(
        default=dict,
        verbose_name='优先级分布',
        help_text='例如: {"1": 0.6, "2": 0.3, "3": 0.1}'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='状态')
    total_tasks_simulated = models.IntegerField(default=0, verbose_name='已仿真任务数')
    avg_wait_time = models.FloatField(null=True, blank=True, verbose_name='平均等待时长（时辰）')
    max_wait_time = models.FloatField(null=True, blank=True, verbose_name='最大等待时长（时辰）')
    avg_total_time = models.FloatField(null=True, blank=True, verbose_name='平均总送达时长（时辰）')
    total_delay_count = models.IntegerField(default=0, verbose_name='延误任务数')
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default='', verbose_name='错误信息')

    class Meta:
        verbose_name = '仿真运行'
        verbose_name_plural = '仿真运行'
        ordering = ['-created_at']

    def __str__(self):
        return f'#{self.pk} {self.name}'


class SimTask(models.Model):
    simulation = models.ForeignKey(SimulationRun, on_delete=models.CASCADE, related_name='sim_tasks', verbose_name='仿真运行')
    task = models.ForeignKey(DeliveryTask, on_delete=models.SET_NULL, null=True, blank=True, related_name='sim_tasks', verbose_name='关联递送任务')
    sim_task_code = models.CharField(max_length=50, verbose_name='仿真任务编号')
    origin_id = models.IntegerField(verbose_name='起点驿站ID')
    destination_id = models.IntegerField(verbose_name='终点驿站ID')
    priority = models.IntegerField(default=1, verbose_name='优先级')
    departure_time = models.FloatField(verbose_name='出发时间（时辰）')
    arrival_time = models.FloatField(null=True, blank=True, verbose_name='实际送达时间（时辰）')
    expected_time = models.FloatField(null=True, blank=True, verbose_name='预计送达时间（无拥堵）')
    deadline = models.FloatField(null=True, blank=True, verbose_name='要求时限')
    total_wait_time = models.FloatField(default=0.0, verbose_name='总等待时长（时辰）')
    max_wait_at_station = models.FloatField(default=0.0, verbose_name='单站最大等待（时辰）')
    station_count = models.IntegerField(default=0, verbose_name='途经驿站数')
    is_delayed = models.BooleanField(default=False, verbose_name='是否延误')
    delay_minutes = models.FloatField(default=0.0, verbose_name='延误时长（时辰）')

    class Meta:
        verbose_name = '仿真任务'
        verbose_name_plural = '仿真任务'
        ordering = ['simulation', 'departure_time']

    def __str__(self):
        return f'{self.sim_task_code}'


class SimStationVisit(models.Model):
    EVENT_TYPE_CHOICES = [
        ('arrive', '到达'),
        ('queue_enter', '进入排队'),
        ('process_start', '开始处理'),
        ('process_end', '处理完成'),
        ('depart', '离开'),
    ]

    sim_task = models.ForeignKey(SimTask, on_delete=models.CASCADE, related_name='station_visits', verbose_name='仿真任务')
    station_id = models.IntegerField(verbose_name='驿站ID')
    station_code = models.CharField(max_length=20, verbose_name='驿站编号')
    visit_order = models.IntegerField(verbose_name='访问顺序')
    arrive_time = models.FloatField(null=True, blank=True, verbose_name='到达时间')
    queue_enter_time = models.FloatField(null=True, blank=True, verbose_name='进入排队时间')
    process_start_time = models.FloatField(null=True, blank=True, verbose_name='开始处理时间')
    process_end_time = models.FloatField(null=True, blank=True, verbose_name='处理完成时间')
    depart_time = models.FloatField(null=True, blank=True, verbose_name='离开时间')
    wait_duration = models.FloatField(default=0.0, verbose_name='排队等待时长（时辰）')
    process_duration = models.FloatField(default=0.0, verbose_name='处理时长（时辰）')
    queue_position_on_arrival = models.IntegerField(default=0, verbose_name='到达时队列长度')
    in_peak_hour = models.BooleanField(default=False, verbose_name='是否在高峰时段')

    class Meta:
        verbose_name = '仿真驿站访问'
        verbose_name_plural = '仿真驿站访问'
        ordering = ['sim_task', 'visit_order']

    def __str__(self):
        return f'{self.sim_task.sim_task_code} @ {self.station_code}'


class SimStationSnapshot(models.Model):
    simulation = models.ForeignKey(SimulationRun, on_delete=models.CASCADE, related_name='station_snapshots', verbose_name='仿真运行')
    station_id = models.IntegerField(verbose_name='驿站ID')
    station_code = models.CharField(max_length=20, verbose_name='驿站编号')
    snapshot_time = models.FloatField(verbose_name='快照时间（时辰）')
    queue_length = models.IntegerField(default=0, verbose_name='排队长度')
    busy_windows = models.IntegerField(default=0, verbose_name='忙碌窗口数')
    total_windows = models.IntegerField(default=1, verbose_name='总窗口数')
    utilization = models.FloatField(default=0.0, verbose_name='利用率（%）')
    in_peak_hour = models.BooleanField(default=False, verbose_name='是否在高峰时段')

    class Meta:
        verbose_name = '驿站快照'
        verbose_name_plural = '驿站快照'
        ordering = ['simulation', 'station_id', 'snapshot_time']


class RoadBlockadeEvent(models.Model):
    EVENT_TYPE_CHOICES = [
        ('road_blocked', '道路封锁'),
        ('road_restricted', '半封闭限流'),
        ('station_down', '驿站停摆'),
        ('military_priority', '军务优先通行'),
    ]
    event_type = models.CharField(max_length=25, choices=EVENT_TYPE_CHOICES, verbose_name='事件类型')
    name = models.CharField(max_length=200, verbose_name='事件名称')
    description = models.TextField(blank=True, default='', verbose_name='描述')
    road = models.ForeignKey(Road, on_delete=models.CASCADE, null=True, blank=True, related_name='blockade_events', verbose_name='影响道路')
    station = models.ForeignKey(Station, on_delete=models.CASCADE, null=True, blank=True, related_name='blockade_events', verbose_name='影响驿站')
    start_hour = models.FloatField(verbose_name='开始时间（时辰，0-24）')
    end_hour = models.FloatField(verbose_name='结束时间（时辰，0-24）')
    severity = models.FloatField(default=1.0, verbose_name='严重程度（1-10）')
    flow_rate = models.FloatField(default=0.0, verbose_name='通行率（0=完全封锁，1=正常通行）')
    reroute_cost_multiplier = models.FloatField(default=1.0, verbose_name='改道成本倍率')
    military_priority_level = models.IntegerField(default=3, verbose_name='军务优先等级（1-3）')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '封锁事件'
        verbose_name_plural = '封锁事件'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_event_type_display()} - {self.name}'

    def clean(self):
        super().clean()
        if self.start_hour < 0 or self.start_hour >= 24:
            raise ValidationError({'start_hour': '开始时间必须在 0-24 时辰之间'})
        if self.end_hour <= 0 or self.end_hour > 24:
            raise ValidationError({'end_hour': '结束时间必须在 0-24 时辰之间'})
        if self.start_hour >= self.end_hour:
            raise ValidationError('开始时间必须早于结束时间')
        if self.severity < 1 or self.severity > 10:
            raise ValidationError({'severity': '严重程度必须在 1-10 之间'})
        if self.flow_rate < 0 or self.flow_rate > 1:
            raise ValidationError({'flow_rate': '通行率必须在 0-1 之间'})
        if not self.road_id and not self.station_id:
            raise ValidationError('必须指定影响道路或影响驿站')
        if self.event_type in ('road_blocked', 'road_restricted') and not self.road_id:
            raise ValidationError('道路封锁/限流事件必须指定影响道路')
        if self.event_type == 'station_down' and not self.station_id:
            raise ValidationError('驿站停摆事件必须指定影响驿站')


class BlockadeDrill(models.Model):
    STATUS_CHOICES = [
        ('pending', '待推演'),
        ('running', '推演中'),
        ('completed', '已完成'),
        ('failed', '推演失败'),
    ]
    name = models.CharField(max_length=200, verbose_name='推演名称')
    description = models.TextField(blank=True, default='', verbose_name='描述')
    base_simulation = models.ForeignKey(SimulationRun, on_delete=models.CASCADE, related_name='blockade_drills', verbose_name='基准仿真')
    blockade_events = models.ManyToManyField(RoadBlockadeEvent, related_name='drills', verbose_name='封锁事件')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='状态')

    before_avg_wait = models.FloatField(null=True, blank=True, verbose_name='封锁前平均等待(时辰)')
    before_max_wait = models.FloatField(null=True, blank=True, verbose_name='封锁前最大等待(时辰)')
    before_avg_total = models.FloatField(null=True, blank=True, verbose_name='封锁前平均送达(时辰)')
    before_delay_count = models.IntegerField(null=True, blank=True, verbose_name='封锁前延误数')
    before_bottleneck_codes = models.JSONField(default=list, verbose_name='封锁前瓶颈驿站列表')

    after_avg_wait = models.FloatField(null=True, blank=True, verbose_name='封锁后平均等待(时辰)')
    after_max_wait = models.FloatField(null=True, blank=True, verbose_name='封锁后最大等待(时辰)')
    after_avg_total = models.FloatField(null=True, blank=True, verbose_name='封锁后平均送达(时辰)')
    after_delay_count = models.IntegerField(null=True, blank=True, verbose_name='封锁后延误数')
    after_bottleneck_codes = models.JSONField(default=list, verbose_name='封锁后瓶颈驿站列表')

    reroute_cost_total = models.FloatField(default=0.0, verbose_name='总改道成本')
    affected_task_count = models.IntegerField(default=0, verbose_name='受影响任务数')
    congestion_transfer = models.JSONField(default=dict, verbose_name='拥堵转移数据')
    impact_timeline = models.JSONField(default=list, verbose_name='事件影响时间轴')
    recovery_strategies = models.JSONField(default=list, verbose_name='恢复策略建议')
    bottleneck_diff = models.JSONField(default=dict, verbose_name='瓶颈变化对比')

    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default='', verbose_name='错误信息')

    class Meta:
        verbose_name = '封锁推演'
        verbose_name_plural = '封锁推演'
        ordering = ['-created_at']

    def __str__(self):
        return f'推演: {self.name}'


class SimBottleneckStation(models.Model):
    simulation = models.ForeignKey(SimulationRun, on_delete=models.CASCADE, related_name='bottleneck_stations', verbose_name='仿真运行')
    station_id = models.IntegerField(verbose_name='驿站ID')
    station_code = models.CharField(max_length=20, verbose_name='驿站编号')
    station_name = models.CharField(max_length=100, verbose_name='驿站名称')
    total_visits = models.IntegerField(default=0, verbose_name='总访问次数')
    avg_wait_time = models.FloatField(default=0.0, verbose_name='平均等待时长（时辰）')
    max_wait_time = models.FloatField(default=0.0, verbose_name='最大等待时长（时辰）')
    total_wait_time = models.FloatField(default=0.0, verbose_name='累计等待时长（时辰）')
    avg_queue_length = models.FloatField(default=0.0, verbose_name='平均排队长度')
    max_queue_length = models.IntegerField(default=0, verbose_name='最大排队长度')
    avg_utilization = models.FloatField(default=0.0, verbose_name='平均利用率（%）')
    peak_queue_count = models.IntegerField(default=0, verbose_name='高峰拥堵次数')
    bottleneck_score = models.FloatField(default=0.0, verbose_name='瓶颈评分')
    rank = models.IntegerField(default=0, verbose_name='瓶颈排名')

    class Meta:
        verbose_name = '瓶颈驿站'
        verbose_name_plural = '瓶颈驿站'
        ordering = ['simulation', 'rank']
