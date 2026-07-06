import random as rdm

def secret_sharing(secret):
    if isinstance(secret, int):
        s1=rdm.randrange(1,secret)
        s2=rdm.randrange(1,secret)
        s3=secret-(s1+s2)
        shares = [s1,s2,s3]
    else:
        s1=rdm.uniform(1, secret)
        s2=rdm.uniform(1, secret)
        s3=secret-(s1+s2)
        shares = [s1,s2,s3]

    return shares