import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user_id = session["user_id"]
    benefit = 0
    purchases = db.execute("SELECT symbol, AVG(price) as price, SUM(quantity) as quantity, SUM(total) as total FROM purchases WHERE user_id = :id GROUP BY symbol",
                          id = user_id)
    for purchase in purchases:
        stock = lookup(purchase["symbol"])
        purchase["current_price"] = stock["price"]
        purchase["current_price_usd"] = usd(stock["price"])
        purchase["plus"] = (stock["price"] - purchase["price"]) / purchase["price"]
        purchase["profit"] = (purchase["total"] * purchase["plus"]) + purchase["total"]
        purchase["profit_usd"] = usd(purchase["profit"])
        benefit += purchase["profit"]

    user = db.execute("SELECT cash FROM users WHERE id = :id",
                          id = user_id)
    cash = user[0]["cash"]

    return render_template("index.html", purchases=purchases, cash_usd=usd(cash + benefit), benefit=benefit)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide a symbol", 403)

        symbol = request.form.get("symbol")
        stock = lookup(symbol)

        if stock == None:
            return apology("Stock could not be found")

        # Ensure symbol was submitted
        if not request.form.get("shares"):
            return apology("must provide a positive integer", 403)

        user_id = session["user_id"]
        user = db.execute("SELECT cash FROM users WHERE id = :id",
                          id = user_id)

        shares = request.form.get("shares")
        total = stock["price"] * float(shares)

        new_cash = float(user[0]["cash"]) - total

        if (new_cash < 0):
            return apology("sorry! you don't have enough cash", 403)
        else:
            db.execute("INSERT INTO purchases (user_id, symbol, price, total, quantity) VALUES (:user_id, :symbol, :price, :total, :quantity)",
                        user_id = user_id, symbol = symbol, price = stock["price"], total = total, quantity = shares)
            db.execute("UPDATE users SET cash=:new_cash WHERE id = :user_id",
                        new_cash = new_cash, user_id = user_id)
            return redirect("/")
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    purchases = db.execute("SELECT symbol, price, quantity, bought_at FROM purchases WHERE user_id = :user_id ORDER BY bought_at ASC", user_id=session["user_id"])

    return render_template("history.html", purchases=purchases)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "POST":
        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide a symbol", 403)

        stock = lookup(request.form.get("symbol"))

        if stock == None:
            return apology("Stock could not be found")

        return render_template("quoted.html", stock=stock)

    else:
        return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))
        # Ensure username doesn't exist
        if len(rows) > 0:
            return apology("username already exists! choose another please", 403)

        # Query database for username
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
                          username=request.form.get("username"), hash=generate_password_hash(request.form.get("password")))

        # Redirect user to login
        return redirect("/login")

    # User reached route via GET
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    user_id = session["user_id"]
    stocks = db.execute("SELECT symbol, SUM(quantity) as total_quantity FROM purchases WHERE user_id = :id GROUP BY symbol",
                          id = user_id)

    if request.method == "POST":
        symbol = request.form.get("symbol")
        quote = lookup(symbol)
        # Ensure symbol was submitted
        if not symbol:
            return apology("must provide a symbol", 403)

        if len(stocks) == 0:
            return apology("Stock could not be found")

        if quote == None:
            return apology("invalid symbol", 403)

        try:
            shares = int(request.form.get("shares"))
        except:
            return apology("shares must be a positive integer", 403)

        # Check if number of shares requested was 0
        if shares <= 0:
            return apology("can't sell less than or 0 shares", 403)

        # Check if we have enough shares
        stock = db.execute("SELECT SUM(quantity) as total_quantity FROM purchases WHERE user_id = :user_id AND symbol = :symbol GROUP BY symbol",
                           user_id=user_id, symbol=request.form.get("symbol"))

        print(stock)
        if stock[0]["total_quantity"] <= 0 or stock[0]["total_quantity"] < shares:
            return apology("you can't sell less than 0 or more than you own", 403)

        # Query database for user cash
        user = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=user_id)

        # How much $$$ the user still has in her account
        cash_remaining = user[0]["cash"]
        price_per_share = quote["price"]

        # Calculate the price of requested shares
        total_price = price_per_share * shares

        # Book keeping (TODO: should be wrapped with a transaction)
        db.execute("UPDATE users SET cash = cash + :price WHERE id = :user_id", price=total_price, user_id=user_id)
        db.execute("INSERT INTO purchases (user_id, symbol, price, quantity, total) VALUES(:user_id, :symbol, :price, :quantity, :total)",
                   user_id=user_id,
                   symbol=request.form.get("symbol"),
                   price=price_per_share,
                   quantity=-shares,
                   total = -total_price)

        return redirect("/")
    else:
        return render_template("sell.html", stocks=stocks)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
