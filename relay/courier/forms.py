from django import forms
from .models import Station, Road, HorseChangeStrategy, WeatherRecord, DeliveryTask, DeliverySegment


class StationForm(forms.ModelForm):
    class Meta:
        model = Station
        fields = ['code', 'name', 'latitude', 'longitude', 'capacity', 'process_time', 'description']
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


class RoadForm(forms.ModelForm):
    class Meta:
        model = Road
        fields = ['from_station', 'to_station', 'distance', 'slope', 'grade']
        widgets = {
            'from_station': forms.Select(attrs={'class': 'form-select'}),
            'to_station': forms.Select(attrs={'class': 'form-select'}),
        }

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


class HorseChangeStrategyForm(forms.ModelForm):
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


class WeatherRecordForm(forms.ModelForm):
    class Meta:
        model = WeatherRecord
        fields = ['road', 'weather_type']


class DeliveryTaskForm(forms.ModelForm):
    class Meta:
        model = DeliveryTask
        fields = ['task_code', 'origin', 'destination', 'strategy', 'priority', 'deadline_hours', 'departure_offset', 'selected_plan_type']
        widgets = {
            'origin': forms.Select(attrs={'class': 'form-select'}),
            'destination': forms.Select(attrs={'class': 'form-select'}),
            'strategy': forms.Select(attrs={'class': 'form-select'}),
            'selected_plan_type': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        origin = cleaned_data.get('origin')
        destination = cleaned_data.get('destination')
        if origin and destination and origin == destination:
            raise forms.ValidationError('起点和终点不能相同')
        return cleaned_data


class DeliverySegmentForm(forms.ModelForm):
    class Meta:
        model = DeliverySegment
        fields = ['override_strategy', 'override_weather', 'departure_time']
        widgets = {
            'override_strategy': forms.Select(attrs={'class': 'form-select'}),
            'override_weather': forms.Select(attrs={'class': 'form-select'}),
        }


class DeliveryTaskStatusForm(forms.ModelForm):
    class Meta:
        model = DeliveryTask
        fields = ['status']

    def clean_status(self):
        status = self.cleaned_data.get('status')
        if status == 'executable' and self.instance and self.instance.has_high_risk:
            raise forms.ValidationError('存在高风险断点，不能标记为可执行')
        return status
