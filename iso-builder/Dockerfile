# AquaOS-Beta Automated ISO Builder Container (Ubuntu 24.04.2 LTS Noble Numbat Edition)
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    debootstrap \
    squashfs-tools \
    xorriso \
    grub-pc-bin \
    grub-efi-amd64-bin \
    grub-common \
    mtools \
    dosfstools \
    software-properties-common \
    ubuntu-keyring \
    ca-certificates \
    curl \
    python3 \
    python3-pytest \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
CMD ["bash", "/workspace/iso-builder/build-iso.sh"]
