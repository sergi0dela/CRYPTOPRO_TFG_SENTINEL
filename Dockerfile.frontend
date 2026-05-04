# Usamos Nginx, que es un servidor web muy rápido
FROM nginx:stable-alpine

# Copiamos tu index.html a la carpeta de Nginx
COPY . /usr/share/nginx/html

# Exponemos el puerto 80
EXPOSE 80

# Arrancamos Nginx
CMD ["nginx", "-g", "daemon off;"]