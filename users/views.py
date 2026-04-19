# users/views.py

from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
import re
from django.utils import timezone
from datetime import timedelta
from .models import User, UserAddress, UserSession
from .serializers import UserSerializer, UserAddressSerializer
from verification.models import EmailVerification


# ─── Helpers ─────────────────────────────────────────────────────────────────

def get_user_from_token(request):
    """Extract user from Authorization header — supports both Token and Bearer."""
    auth_header = request.headers.get('Authorization', '')

    token_key = None
    if auth_header.startswith('Token '):
        token_key = auth_header.split(' ')[1]
    elif auth_header.startswith('Bearer '):
        token_key = auth_header.split(' ')[1]

    if not token_key:
        return None

    # Check DRF authtoken table first
    try:
        token_obj = Token.objects.select_related('user').get(key=token_key)
        return token_obj.user
    except Token.DoesNotExist:
        pass

    # Fall back to legacy UserSession table
    try:
        session = UserSession.objects.filter(token=token_key).first()
        if not session:
            return None
        if session.expires_at < timezone.now():
            session.delete()
            return None
        return session.user
    except Exception:
        return None


# ─── Auth ─────────────────────────────────────────────────────────────────────

@api_view(['POST'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def register(request):
    """Register a new user — requires email verification before login."""
    import sys

    try:
        username = request.data.get('username', '').strip()
        email    = request.data.get('email', '').strip()
        password = request.data.get('password', '')

        if not username:
            return Response({'error': 'Username is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not email:
            return Response({'error': 'Email is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not password:
            return Response({'error': 'Password is required.'}, status=status.HTTP_400_BAD_REQUEST)

        if not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
            return Response({'error': 'Please enter a valid email address.'}, status=status.HTTP_400_BAD_REQUEST)

        if len(password) < 8:
            return Response({'error': 'Password must be at least 8 characters.'}, status=status.HTTP_400_BAD_REQUEST)

        existing_user = User.objects.filter(email=email).first()
        if existing_user:
            if existing_user.email_verified:
                return Response({'error': 'Email already registered.'}, status=status.HTTP_400_BAD_REQUEST)
            else:
                existing_user.delete()

        if User.objects.filter(username=username).exists():
            return Response({'error': 'Username already taken.'}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            is_active=True,
            email_verified=False,
        )

        from verification.email_service import generate_6digit_code, send_verification_email

        EmailVerification.objects.filter(email=email, is_verified=False).delete()

        code       = generate_6digit_code()
        expires_at = timezone.now() + timedelta(minutes=15)

        EmailVerification.objects.create(
            email=email,
            code=code,
            purpose='email_verify',
            user_id=user.user_id,
            expires_at=expires_at,
        )

        try:
            send_verification_email(email, code, 'email_verify')
            print(f"[REGISTER] Verification email sent to {email}", file=sys.stderr, flush=True)
        except Exception as email_err:
            print(f"[REGISTER] Email sending failed: {email_err}", file=sys.stderr, flush=True)

        return Response(
            {
                'message': 'Registration successful. Please check your email for the verification code.',
                'user_id': str(user.user_id),
                'email': user.email,
                'username': user.username,
                'email_verified': False,
                'verification_required': True,
            },
            status=status.HTTP_201_CREATED,
        )
    except Exception as e:
        print(f"[REGISTER] Error: {e}", file=sys.stderr, flush=True)
        return Response({'error': 'Registration failed. Please try again.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def login(request):
    """Login and return DRF token."""
    email    = request.data.get('email', '').strip()
    password = request.data.get('password', '')

    if not email or not password:
        return Response({'error': 'Email and password are required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.filter(email=email).first()
        if not user:
            return Response({'error': 'Invalid email or password.'}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_active:
            return Response({'error': 'Account is disabled.'}, status=status.HTTP_403_FORBIDDEN)

        if not user.email_verified:
            return Response(
                {'error': 'Please verify your email before logging in.', 'code': 'email_not_verified'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not user.check_password(password):
            return Response({'error': 'Invalid email or password.'}, status=status.HTTP_401_UNAUTHORIZED)

        # ── Use DRF token ─────────────────────────────────────────────────────
        token, _ = Token.objects.get_or_create(user=user)

        user.last_login    = timezone.now()
        user.last_login_ip = request.META.get('REMOTE_ADDR', '')
        user.save()

        return Response({
            'token': token.key,
            'user': {
                'user_id':    str(user.user_id),
                'email':      user.email,
                'username':   user.username,
                'first_name': user.first_name,
                'last_name':  user.last_name,
                'user_type':  user.user_type,
            },
        })

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def logout(request):
    """Invalidate token."""
    auth_header = request.headers.get('Authorization', '')

    token_key = None
    if auth_header.startswith('Token '):
        token_key = auth_header.split(' ')[1]
    elif auth_header.startswith('Bearer '):
        token_key = auth_header.split(' ')[1]

    if not token_key:
        return Response({'error': 'No token provided.'}, status=status.HTTP_400_BAD_REQUEST)

    Token.objects.filter(key=token_key).delete()
    UserSession.objects.filter(token=token_key).delete()

    return Response({'message': 'Logged out successfully.'})


@api_view(['POST'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def verify_email(request):
    """Verify user email with 6-digit code."""
    email = request.data.get('email', '').strip()
    code  = request.data.get('code', '').strip()

    if not email or not code:
        return Response({'error': 'Email and code are required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        verification = EmailVerification.objects.get(email=email, code=code, is_verified=False)
    except EmailVerification.DoesNotExist:
        return Response({'error': 'Invalid verification code.'}, status=status.HTTP_400_BAD_REQUEST)

    if not verification.is_valid():
        verification.delete()
        return Response({'error': 'Verification code expired. Request a new one.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

    user.email_verified = True
    user.save()

    verification.is_verified = True
    verification.save()

    try:
        from verification.email_service import send_welcome_email
        send_welcome_email(user.email, user.username)
    except Exception:
        pass

    return Response({'message': 'Email verified successfully! You can now log in.', 'email_verified': True})


@api_view(['POST'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def resend_verification(request):
    """Resend verification code."""
    email = request.data.get('email', '').strip()

    if not email:
        return Response({'error': 'Email is required.'}, status=status.HTTP_400_BAD_REQUEST)

    user = User.objects.filter(email=email).first()
    if not user:
        return Response({'error': 'No account found with this email.'}, status=status.HTTP_404_NOT_FOUND)

    if user.email_verified:
        return Response({'message': 'Email already verified.'})

    from verification.email_service import generate_6digit_code, send_verification_email

    EmailVerification.objects.filter(email=email, is_verified=False).delete()

    code       = generate_6digit_code()
    expires_at = timezone.now() + timedelta(minutes=15)

    EmailVerification.objects.create(
        email=email,
        code=code,
        purpose='email_verify',
        user=user,
        expires_at=expires_at,
    )

    send_verification_email(email, code, 'email_verify')

    return Response({'message': 'Verification code sent. Check your email.'})


@api_view(['GET'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def verification_status(request):
    """Check if the current user's email is verified."""
    user = get_user_from_token(request)
    if not user:
        return Response({'error': 'Unauthorized.'}, status=status.HTTP_401_UNAUTHORIZED)
    return Response({'email_verified': user.email_verified})


# ─── Profile ──────────────────────────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def get_profile(request):
    user = get_user_from_token(request)
    if not user:
        return Response({'error': 'Unauthorized. Please log in.'}, status=status.HTTP_401_UNAUTHORIZED)
    serializer = UserSerializer(user)
    return Response(serializer.data)


@api_view(['PUT', 'PATCH'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def update_profile(request):
    user = get_user_from_token(request)
    if not user:
        return Response({'error': 'Unauthorized. Please log in.'}, status=status.HTTP_401_UNAUTHORIZED)

    data = request.data.copy()
    data.pop('email', None)
    data.pop('username', None)
    data.pop('password', None)

    serializer = UserSerializer(user, data=data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def change_password(request):
    """Change user password."""
    user = get_user_from_token(request)
    if not user:
        return Response({'error': 'Unauthorized. Please log in.'}, status=status.HTTP_401_UNAUTHORIZED)

    old_password = request.data.get('old_password', '')
    new_password = request.data.get('new_password', '')

    if not old_password or not new_password:
        return Response({'error': 'old_password and new_password are required.'}, status=status.HTTP_400_BAD_REQUEST)

    if not user.check_password(old_password):
        return Response({'error': 'Current password is incorrect.'}, status=status.HTTP_400_BAD_REQUEST)

    if len(new_password) < 8:
        return Response({'error': 'New password must be at least 8 characters.'}, status=status.HTTP_400_BAD_REQUEST)

    user.set_password(new_password)
    user.save()

    # Refresh DRF token after password change
    Token.objects.filter(user=user).delete()
    Token.objects.create(user=user)

    return Response({'message': 'Password changed successfully.'})


# ─── Addresses ────────────────────────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def address_list(request):
    user = get_user_from_token(request)
    if not user:
        return Response({'error': 'Unauthorized. Please log in.'}, status=status.HTTP_401_UNAUTHORIZED)
    addresses  = UserAddress.objects.filter(user=user)
    serializer = UserAddressSerializer(addresses, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def create_address(request):
    user = get_user_from_token(request)
    if not user:
        return Response({'error': 'Unauthorized. Please log in.'}, status=status.HTTP_401_UNAUTHORIZED)

    data         = request.data.copy()
    data['user'] = str(user.user_id)

    serializer = UserAddressSerializer(data=data)
    if serializer.is_valid():
        address = serializer.save()
        return Response(UserAddressSerializer(address).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def address_detail(request, address_id):
    user = get_user_from_token(request)
    if not user:
        return Response({'error': 'Unauthorized. Please log in.'}, status=status.HTTP_401_UNAUTHORIZED)
    try:
        address = UserAddress.objects.get(address_id=address_id, user=user)
        return Response(UserAddressSerializer(address).data)
    except UserAddress.DoesNotExist:
        return Response({'error': 'Address not found.'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['PUT', 'PATCH'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def update_address(request, address_id):
    user = get_user_from_token(request)
    if not user:
        return Response({'error': 'Unauthorized. Please log in.'}, status=status.HTTP_401_UNAUTHORIZED)
    try:
        address    = UserAddress.objects.get(address_id=address_id, user=user)
        serializer = UserAddressSerializer(address, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    except UserAddress.DoesNotExist:
        return Response({'error': 'Address not found.'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['DELETE'])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def delete_address(request, address_id):
    user = get_user_from_token(request)
    if not user:
        return Response({'error': 'Unauthorized. Please log in.'}, status=status.HTTP_401_UNAUTHORIZED)
    try:
        address = UserAddress.objects.get(address_id=address_id, user=user)
        address.delete()
        return Response({'message': 'Address deleted.'}, status=status.HTTP_204_NO_CONTENT)
    except UserAddress.DoesNotExist:
        return Response({'error': 'Address not found.'}, status=status.HTTP_404_NOT_FOUND)