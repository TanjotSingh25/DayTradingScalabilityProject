from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework import status
from rest_framework.permissions import AllowAny
from .serializers import RegisterSerializer
from django.contrib.auth.hashers import make_password, check_password
from .models import Users


@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    if request.method == 'POST':
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user_name = serializer.validated_data.get('user_name')
            password = serializer.validated_data.get('password')
            name = serializer.validated_data.get('name')

            if Users.objects.filter(user_name=user_name).exists():
                return Response(
                    {"success": False, "data": {"error": "Username already exists"}},
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                hashed_password = make_password(password)
                user = Users.objects.create(user_name=user_name, password=hashed_password, name=name)
                return Response(
                    {"success": True, "data": None},
                    status=status.HTTP_201_CREATED
                )
            except Exception as e:
                return Response(
                    {"success": False, "data": {"error": str(e)} },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        return Response(
            {"success": False, "data": {"error": "Invalid data"}},
            status=status.HTTP_400_BAD_REQUEST
        )

@api_view(['POST'])
def login(request):
    user_name = request.data.get('user_name')
    password = request.data.get('password')

    try:
        user = Users.objects.get(user_name=user_name)
        if check_password(password, user.password):
            refresh = RefreshToken()
            refresh.payload['user_id'] = user.id  
            refresh.payload['user_name'] = user.user_name

            return Response({
                'success': True,
                'data': {'token': str(refresh.access_token)}
            })
        else:
            return Response({
                'success': False,
                'data': {'error': 'Invalid password'}
            }, status=status.HTTP_401_UNAUTHORIZED)
    except Users.DoesNotExist:
        return Response({
            'success': False,
            'data': {'error': 'User not found'}
        }, status=status.HTTP_404_NOT_FOUND)

@api_view(['DELETE'])
def delete(request, user_name):
    try:
        user = Users.objects.get(user_name=user_name)
        user.delete()
        return Response(
            {"success": True, "data": None},
            status=status.HTTP_204_NO_CONTENT
        )
    except Users.DoesNotExist:
        return Response(
            {"success": False, "data": {"error": "User not found"}},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {"success": False, "data": {"error": str(e)}},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
