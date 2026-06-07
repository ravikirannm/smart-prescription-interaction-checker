# Use Node.js for the build/dev environment
FROM node:20

# Set the working directory inside the container
WORKDIR /app

# Copy package files first (to cache layers)
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy the rest of the frontend code
COPY . .

# Expose the Angular port
EXPOSE 4200

# Run the Angular dev server
# --host 0.0.0.0 is required for Docker to allow external access
CMD ["npx", "ng", "serve", "--host", "0.0.0.0"]