"""
Google OAuth integration for NiceGUI
Based on: https://luckywolf.medium.com/python-nicegui-and-google-oauth-7d801325874f
"""

import os
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from nicegui import app, ui
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from user import User
from datetime import datetime

# Load environment variables
config = Config('.env')

# OAuth setup
oauth = OAuth(config)
oauth.register(
    name='google',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

# Database
database_url = os.getenv('DATABASE_URL')
engine = create_engine(database_url)
Session = sessionmaker(bind=engine)


from starlette.requests import Request
from starlette.responses import RedirectResponse

@app.get('/auth/google/login')
async def google_login(request: Request):
    """Initiate Google OAuth login"""
    redirect_uri = str(request.url_for('google_callback'))
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get('/auth/google/callback')
async def google_callback(request: Request):
    """Handle Google OAuth callback"""
    
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        
        if not user_info:
            return RedirectResponse(url='/login?error=no_user_info')
        
        email = user_info.get('email')
        
        if not email:
            return RedirectResponse(url='/login?error=no_email')
        
        # Check if user exists, create if not
        session = Session()
        user = session.query(User).filter_by(email=email).first()
        
        if not user:
            # Create new user from Google account
            user = User(
                email=email,
                password_hash='',  # No password for OAuth users
                role='student',  # Default role, adjust as needed
                is_active=True
            )
            session.add(user)
            session.commit()
        
        # Update last login
        user.last_login = datetime.utcnow()
        
        # Save user data before closing
        user_id = user.id
        user_email = user.email
        user_role = user.role
        
        session.commit()
        session.close()
        
        # Store in session
        app.storage.user['authenticated'] = True
        app.storage.user['user_id'] = user_id
        app.storage.user['email'] = user_email
        app.storage.user['role'] = user_role
        app.storage.user['oauth_provider'] = 'google'
        
        # Redirect to admin
        return RedirectResponse(url='/admin')
        
    except Exception as e:
        print(f"OAuth error: {e}")
        import traceback
        traceback.print_exc()
        return RedirectResponse(url='/login?error=oauth_failed')


def add_google_login_button():
    """Add Google Sign In button to login page"""
    with ui.link(
        target='/auth/google/login',
        new_tab=False
    ).classes('w-full').style('text-decoration: none;'):
        with ui.row().classes('w-full bg-white border border-gray-300 rounded px-4 py-2 items-center justify-center gap-3 hover:bg-gray-50 cursor-pointer'):
            ui.html('''
                <svg width="18" height="18" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">
                    <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
                    <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
                    <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
                    <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
                </svg>
            ''', sanitize=False)
            ui.label('Sign in with Google').classes('text-gray-700 font-medium')