from pyngrok import ngrok

ngrok.set_auth_token(3CM6zTQYW48TbTBfjatJxkgBKU5_5QCSm6nvM4Dnjqqbht5jg)


public_url = ngrok.connect(5000)
print("URL publica:", public_url)