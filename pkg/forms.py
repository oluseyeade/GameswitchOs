from flask_wtf import FlaskForm
from wtforms import PasswordField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length


class RegisterForm(FlaskForm):
    full_name = StringField("Full Name", validators=[DataRequired(), Length(min=2, max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    phone = StringField("Phone", validators=[DataRequired(), Length(min=7, max=40)])
    branch = SelectField(
        "Branch",
        choices=[("branch1", "Branch 1"), ("branch2", "Branch 2")],
        validators=[DataRequired()],
    )
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6, max=128)])
    submit = SubmitField("Register")


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6, max=128)])
    submit = SubmitField("Login")


class PaymentCheckoutForm(FlaskForm):
    branch = SelectField(
        "Branch",
        choices=[("branch1", "Branch 1"), ("branch2", "Branch 2")],
        validators=[DataRequired()],
    )
    game_id = SelectField("Game", coerce=int, validators=[DataRequired()])
    duration_minutes = SelectField(
        "Duration",
        coerce=int,
        choices=[(30, "30 Minutes"), (60, "60 Minutes"), (120, "120 Minutes")],
        validators=[DataRequired()],
    )
    payment_status = SelectField(
        "Payment Outcome",
        choices=[("successful", "Successful"), ("declined", "Declined")],
        validators=[DataRequired()],
    )
    plug_id = StringField("Smart Plug ID", validators=[DataRequired(), Length(max=100)])
    submit = SubmitField("Checkout")


class SessionAdjustForm(FlaskForm):
    delta_seconds = SelectField(
        "Adjust Timer",
        coerce=int,
        choices=[(300, "+5 minutes"), (-300, "-5 minutes")],
        validators=[DataRequired()],
    )
    submit = SubmitField("Apply")
