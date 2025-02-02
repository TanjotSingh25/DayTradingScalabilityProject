from rest_framework import serializers

class RegisterSerializer(serializers.Serializer):
    user_name = serializers.CharField(max_length=255)
    password = serializers.CharField(write_only=True)
    name = serializers.CharField(max_length=255)
    user_type = serializers.ChoiceField(choices=['user', 'company'], default='user')
