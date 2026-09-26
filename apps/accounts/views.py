from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import EmailTokenObtainPairSerializer, SignupSerializer, UserSerializer
from .services import register_user


class SignupView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()  # a stale/garbage Authorization header must not block signup
    throttle_scope = "auth"

    @extend_schema(
        tags=["Auth"],
        summary="Register a new user",
        description="Creates an account. Returns the user (no tokens) — call /auth/login/ next.",
        request=SignupSerializer,
        responses={
            201: UserSerializer,
            400: OpenApiResponse(description="Validation error (email, password, full_name)."),
            409: OpenApiResponse(description="EMAIL_ALREADY_EXISTS"),
        },
    )
    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = register_user(**serializer.validated_data)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    post=extend_schema(
        tags=["Auth"],
        summary="Log in",
        description="Exchange email + password for an access and refresh JWT. "
        "Email is case-insensitive.",
        responses={401: OpenApiResponse(description="Wrong email or password.")},
    )
)
class LoginView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer
    authentication_classes = ()
    throttle_scope = "auth"


@extend_schema_view(
    post=extend_schema(
        tags=["Auth"],
        summary="Refresh access token",
        description="Exchange a valid refresh token for a new access token.",
        responses={401: OpenApiResponse(description="Refresh token invalid or expired.")},
    )
)
class RefreshView(TokenRefreshView):
    authentication_classes = ()


class MeView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        tags=["Auth"],
        summary="Current user",
        description="Returns the user owning the access token.",
        responses={200: UserSerializer, 401: OpenApiResponse(description="Missing/invalid token.")},
    )
    def get(self, request):
        return Response(UserSerializer(request.user).data)
