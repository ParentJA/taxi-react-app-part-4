from decimal import Decimal, ROUND_UP

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db.models import Avg, Count
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Trip


def make_cache_key(driver_id):
    return f'driver:{driver_id}'


class UserSerializer(serializers.ModelSerializer):
    password1 = serializers.CharField(write_only=True)
    password2 = serializers.CharField(write_only=True)
    group = serializers.CharField()
    rating = serializers.SerializerMethodField(allow_null=True, default=None)
    num_trips = serializers.SerializerMethodField(allow_null=True, default=None)

    def get_rating(self, obj):
        if obj.group == 'driver':
            cache_key = make_cache_key(obj.id)
            rating = cache.get(cache_key)
            if rating is None:
                trips = Trip.objects.filter(
                    driver=obj.id, rating__isnull=False
                ).aggregate(
                    Avg('rating'), Count('rating')
                )
                if trips['rating__count'] >= 3:
                    new_rating = Decimal(trips['rating__avg']).quantize(Decimal('.01'), rounding=ROUND_UP)
                    cache.set(cache_key, str(new_rating))
                    return str(new_rating)
                else:
                    cache.set(cache_key, 0)
                    return 0
            else:
                return rating
        return None

    def get_num_trips(self, obj):
        if obj.group == 'driver':
            trips = Trip.objects.filter(
                driver=obj.id
            ).aggregate(
                Count('id')
            )
            return trips['id__count']
        return None

    def validate(self, data):
        if data['password1'] != data['password2']:
            raise serializers.ValidationError('Passwords must match.')
        return data

    def create(self, validated_data):
        group_data = validated_data.pop('group')
        group, _ = Group.objects.get_or_create(name=group_data)
        data = {
            key: value for key, value in validated_data.items()
            if key not in ('password1', 'password2')
        }
        data['password'] = validated_data['password1']
        user = self.Meta.model.objects.create_user(**data)
        user.groups.add(group)
        user.save()
        return user

    class Meta:
        model = get_user_model()
        fields = (
            'id', 'username', 'password1', 'password2',
            'first_name', 'last_name', 'group',
            'photo', 'rating', 'num_trips',
        )
        read_only_fields = ('id',)


class LogInSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        user_data = UserSerializer(user).data
        for key, value in user_data.items():
            if key != 'id':
                token[key] = value
        return token


class TripSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trip
        fields = '__all__'
        read_only_fields = ('id', 'created', 'updated',)


class NestedTripSerializer(serializers.ModelSerializer):
    driver = UserSerializer(read_only=True)
    rider = UserSerializer(read_only=True)

    class Meta:
        model = Trip
        fields = '__all__'
        read_only_fields = (
            'id', 'created', 'updated', 'pick_up_address', 'drop_off_address',
        )
        depth = 1
