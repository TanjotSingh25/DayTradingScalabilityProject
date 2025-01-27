from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework import status
from rest_framework.permissions import AllowAny
from .serializers import RegisterSerializer
from django.contrib.auth.models import User

# Register API for creating a new user
@api_view(['POST'])
@permission_classes([AllowAny])  # This allows the endpoint to be accessed by anyone
def register(request): #hash passowrds
    if request.method == 'POST':
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            username = serializer.validated_data.get('username')
            password = serializer.validated_data.get('password')
            name = serializer.validated_data.get('name')

            if User.objects.filter(username=username).exists():
                return Response(
                    {"success": False, "data": None, "message": "Username already exists"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                user = User.objects.create_user(username=username, password=password)
                user.first_name = name
                user.save()
                return Response(
                    {"success": True, "data": None},
                    status=status.HTTP_201_CREATED
                )
            except Exception as e:
                return Response(
                    {"success": False, "data": None, "message": str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        return Response(
            {"success": False, "data": None, "message": "Invalid data"},
            status=status.HTTP_400_BAD_REQUEST
        )

@api_view(['POST'])
def login(request):
    username = request.data.get('username')
    password = request.data.get('password')

    try:
        user = User.objects.get(username=username)
        if user.check_password(password):
            refresh = RefreshToken.for_user(user)
            return Response({
                'success': True,
                'data': {'token': str(refresh.access_token)}
            })
        else:
            return Response({
                'success': False,
                'message': 'Invalid password'
            })
    except User.DoesNotExist:
        return Response({
            'success': False,
            'message': 'User not found'
        })
