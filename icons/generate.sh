#!/bin/bash

# Specify the input image and output directory
input_image="/home/me/pixcie/icons/icon_256x256.png"
output_directory="/home/me/pixcie/icons"

# Create the output directory if it doesn't exist
mkdir -p "$output_directory"

# Define the desired icon sizes
sizes=("16x16" "22x22" "24x24" "32x32" "48x48" "64x64" "128x128" "256x256")

# Loop through each size and generate the icons
for size in "${sizes[@]}"; do
  output_filename="icon_${size}.png"
  output_path="${output_directory}/${output_filename}"
  
  # Resize the image to the specified size
  convert "$input_image" -resize "$size" "$output_path"
done

echo "Icons generated successfully!"

