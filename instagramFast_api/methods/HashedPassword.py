from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto",bcrypt__truncate_error=False)

class HashedPassword:
    @staticmethod
    def hash_password(password):
        return pwd_context.hash(password)
    @staticmethod
    def verify_password(password,hashed_password):
        return pwd_context.verify(password, hashed_password)



