import json
from django import forms
from .models import Station, Road, HorseChangeStrategy, WeatherRecord, DeliveryTask, DeliverySegment
from .models import StationPeakHour, SimulationRun


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            existing_classes = field.widget.attrs.get('class', '')
            if isinstance(field.widget, forms.Select):
                field.widget.attrs['class'] = (existing_classes + ' form-select').strip()
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = (existing_classes + ' form-check-input').strip()
            else:
                field.widget.attrs['class'] = (existing_classes + ' form-control').strip()


class StationForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Station
        fields = ['code', 'name', 'latitude', 'longitude', 'capacity', 'window_count', 'process_time', 'queue_rule', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_code(self):
        code = self.cleaned_data.get('code')
        if self.instance and self.instance.pk:
            if Station.objects.filter(code=code).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError('驿站编号不能重复')
        else:
            if Station.objects.filter(code=code).exists():
                raise forms.ValidationError('驿站编号不能重复')
        return code


class StationPeakHourForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = StationPeakHour
        fields = ['station', 'start_hour', 'end_hour', 'capacity_multiplier', 'arrival_multiplier', 'process_delay_pct', 'label']


class SimulationRunForm(BootstrapFormMixin, forms.ModelForm):
    priority_1_pct = forms.IntegerField(
        label='普通任务占比(%)',
        min_value=0, max_value=100, initial=60,
        widget=forms.NumberInput()
    )
    priority_2_pct = forms.IntegerField(
        label='加急任务占比(%)',
        min_value=0, max_value=100, initial=30,
        widget=forms.NumberInput()
    )
    priority_3_pct = forms.IntegerField(
        label='八百里加急占比(%)',
        min_value=0, max_value=100, initial=10,
        widget=forms.NumberInput()
    )

    class Meta:
        model = SimulationRun
        fields = ['name', 'description', 'sim_start_time', 'sim_end_time', 'random_seed', 'task_count', 'enable_peak_hours']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('priority_1_pct', 0)
        p2 = cleaned_data.get('priority_2_pct', 0)
        p3 = cleaned_data.get('priority_3_pct', 0)
        total = p1 + p2 + p3
        if total == 0:
            raise forms.ValidationError('优先级占比总和不能为0')
        cleaned_data['priority_distribution'] = {
            '1': round(p1 / total, 3),
            '2': round(p2 / total, 3),
            '3': round(p3 / total, 3),
        }
        if cleaned_data.get('sim_start_time', 0) >= cleaned_data.get('sim_end_time', 0):
            raise forms.ValidationError('仿真起始时间必须小于结束时间')
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.priority_distribution = self.cleaned_data.get('priority_distribution', {'1': 0.6, '2': 0.3, '3': 0.1})
        if commit:
            instance.save()
        return instance


class RoadForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Road
        fields = ['from_station', 'to_station', 'distance', 'slope', 'grade']

    def clean_distance(self):
        distance = self.cleaned_data.get('distance')
        if distance is not None and distance <= 0:
            raise forms.ValidationError('道路长度必须大于0')
        return distance

    def clean(self):
        cleaned_data = super().clean()
        from_station = cleaned_data.get('from_station')
        to_station = cleaned_data.get('to_station')
        if from_station and to_station and from_station == to_station:
            raise forms.ValidationError('起点和终点不能相同')
        return cleaned_data


class HorseChangeStrategyForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = HorseChangeStrategy
        fields = ['name', 'interval_distance', 'change_time', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_interval_distance(self):
        interval = self.cleaned_data.get('interval_distance')
        if interval is not None and interval < 0:
            raise forms.ValidationError('换马间隔不能为负数')
        return interval


class WeatherRecordForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = WeatherRecord
        fields = ['road', 'weather_type']


class DeliveryTaskForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = DeliveryTask
        fields = ['task_code', 'origin', 'destination', 'strategy', 'priority', 'deadline_hours', 'departure_offset', 'selected_plan_type']

    def clean(self):
        cleaned_data = super().clean()
        origin = cleaned_data.get('origin')
        destination = cleaned_data.get('destination')
        if origin and destination and origin == destination:
            raise forms.ValidationError('起点和终点不能相同')
        return cleaned_data


class DeliverySegmentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = DeliverySegment
        fields = ['override_strategy', 'override_weather', 'departure_time']


class DeliveryTaskStatusForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = DeliveryTask
        fields = ['status']

    def clean_status(self):
        status = self.cleaned_data.get('status')
        if status == 'executable' and self.instance and self.instance.has_high_risk:
            raise forms.ValidationError('存在高风险断点，不能标记为可执行')
        return status
