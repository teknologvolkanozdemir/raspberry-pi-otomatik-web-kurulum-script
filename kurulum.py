#!/usr/bin/env python3
"""Raspberry Pi OS üzerinde web sunucusu kurulumu (Apache, PHP, MariaDB, phpMyAdmin, Pure-FTPd).

Kullanım: sudo python3 kurulum.py
"""
import os
import secrets
import shutil
import subprocess
import sys

BILGI_DOSYASI = "/root/kurulum-bilgileri.txt"
WEB_KOK = "/var/www/html"
FTP_KULLANICI = "ftpuser"
ENV = dict(os.environ, DEBIAN_FRONTEND="noninteractive")


def calistir(komut, girdi=None):
    print("  $ " + " ".join(komut))
    subprocess.run(komut, input=girdi, text=True, env=ENV, check=True)


def apt_kur(*paketler):
    calistir(["apt-get", "install", "-y", *paketler])


def parola_uret():
    return secrets.token_urlsafe(16)


def kontroller():
    if os.geteuid() != 0:
        sys.exit("Hata: Bu script root olarak çalıştırılmalı: sudo python3 kurulum.py")
    if not shutil.which("apt-get"):
        sys.exit("Hata: apt-get bulunamadı. Bu script sadece Raspberry Pi OS (Debian tabanlı) içindir.")


def mariadb_kur():
    apt_kur("mariadb-server", "mariadb-client")
    calistir(["systemctl", "enable", "--now", "mariadb"])
    root_parola = parola_uret()
    pma_parola = parola_uret()
    sql = (
        f"ALTER USER 'root'@'localhost' IDENTIFIED VIA mysql_native_password USING PASSWORD('{root_parola}');\n"
        f"CREATE USER IF NOT EXISTS 'pma'@'localhost' IDENTIFIED BY '{pma_parola}';\n"
        "GRANT ALL PRIVILEGES ON *.* TO 'pma'@'localhost' WITH GRANT OPTION;\n"
        "FLUSH PRIVILEGES;\n"
    )
    calistir(["mysql", "-u", "root"], girdi=sql)
    return root_parola, pma_parola


def phpmyadmin_kur(root_parola, pma_parola):
    secimler = (
        "phpmyadmin phpmyadmin/dbconfig-install boolean false\n"
        "phpmyadmin phpmyadmin/reconfigure-webserver multiselect apache2\n"
    )
    calistir(["debconf-set-selections"], girdi=secimler)
    apt_kur("phpmyadmin")
    calistir(["a2enconf", "phpmyadmin"])


def ftp_kur():
    apt_kur("pure-ftpd")
    ayarlar = {
        "ChrootEveryone": "yes",
        "NoAnonymous": "yes",
        "PureDB": "/etc/pure-ftpd/pureftpd.pdb",
    }
    for ad, deger in ayarlar.items():
        with open(f"/etc/pure-ftpd/conf/{ad}", "w") as f:
            f.write(deger + "\n")
    baglanti = "/etc/pure-ftpd/auth/50pure"
    if not os.path.lexists(baglanti):
        os.symlink("../conf/PureDB", baglanti)
    parola = parola_uret()
    if _ftp_kullanici_var():
        calistir(["pure-pw", "userdel", FTP_KULLANICI, "-m"])
    calistir(
        ["pure-pw", "useradd", FTP_KULLANICI, "-u", "www-data", "-g", "www-data", "-d", WEB_KOK, "-m"],
        girdi=f"{parola}\n{parola}\n",
    )
    calistir(["systemctl", "enable", "pure-ftpd"])
    calistir(["systemctl", "restart", "pure-ftpd"])
    return parola


def _ftp_kullanici_var():
    r = subprocess.run(["pure-pw", "show", FTP_KULLANICI], capture_output=True, env=ENV)
    return r.returncode == 0


def main():
    kontroller()
    print("[1/6] Paket listesi güncelleniyor...")
    calistir(["apt-get", "update"])
    print("[2/6] Apache + PHP kuruluyor...")
    apt_kur("apache2", "php", "libapache2-mod-php", "php-mysql", "php-curl", "php-gd",
            "php-mbstring", "php-xml", "php-zip", "php-intl", "unzip", "curl")
    calistir(["systemctl", "enable", "--now", "apache2"])
    print("[3/6] MariaDB kuruluyor...")
    root_parola, pma_parola = mariadb_kur()
    print("[4/6] phpMyAdmin kuruluyor...")
    phpmyadmin_kur(root_parola, pma_parola)
    print("[5/6] Pure-FTPd kuruluyor...")
    ftp_parola = ftp_kur()
    print("[6/6] Servisler yeniden başlatılıyor...")
    calistir(["chown", "-R", "www-data:www-data", WEB_KOK])
    calistir(["systemctl", "restart", "apache2"])

    ip = subprocess.run(["hostname", "-I"], capture_output=True, text=True).stdout.split()
    ip = ip[0] if ip else "<raspberry-ip>"
    bilgi = (
        f"Web sitesi : http://{ip}/  (dizin: {WEB_KOK})\n"
        f"phpMyAdmin : http://{ip}/phpmyadmin\n"
        f"MariaDB root parolası : {root_parola}\n"
        f"phpMyAdmin kullanıcısı: pma / {pma_parola}\n"
        f"FTP        : {ip}:21  kullanıcı: {FTP_KULLANICI}  parola: {ftp_parola}\n"
    )
    fd = os.open(BILGI_DOSYASI, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(bilgi)
    print("\nKurulum tamamlandı!\n" + bilgi)
    print(f"Bu bilgiler {BILGI_DOSYASI} dosyasına kaydedildi.")


if __name__ == "__main__":
    main()
