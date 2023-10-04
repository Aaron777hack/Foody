import os
import zipfile
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, View
from django.utils import timezone
from .forms import AddProductForm, CheckoutForm, UploadFileForm
from datetime import datetime
from rest_framework import serializers
from .models import Badge
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from .models import (
    Item,
    Order,
    OrderItem,
    CheckoutAddress,
    Payment
)
import logging
import stripe
from .models import Badge
from django.contrib.auth.models import User
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from .models import Badge
from .serializers import BadgeSerializer

stripe.api_key = settings.STRIPE_KEY

@method_decorator(login_required, name='dispatch')
# Create your views here.
class HomeView(ListView):
    model = Item
    template_name = "home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Récupérez l'utilisateur spécifique (par exemple, l'utilisateur connecté)
        user_name = self.request.user
        
        # Récupérez les badges associés à cet utilisateur
        badges = user_name.badge_set.all()

        user = User.objects.get(id=user_name.id)

        date_inscription = user.date_joined

        # Obtenez la date actuelle
        date_actuelle = datetime.now(timezone.utc)

        # Calculez la différence entre la date actuelle et la date d'inscription
        difference = date_actuelle - date_inscription

        # Obtenez le nombre d'années et de mois dans la différence
        nombre_annees = difference.days // 365

        existing_badge = Badge.objects.filter(user=user, label="Pionner").first()
        if not existing_badge:
            if nombre_annees >=1:
                badge = Badge(user=user_name, label="Pionner")
                badge.save()
        # nombre_produits = Item.objects.filter(user=user_name).count()
        # existing_badge = Badge.objects.filter(user=user_name, label="Collector").first()
        # if not existing_badge:
        #     if nombre_produits <5:

        #         badge = Badge.objects.get(user=user_name)
        #         badge.delete()



        
        print(nombre_annees)
        
        # Ajoutez les badges au contexte de la vue
        context['user_badges'] = badges
        
        return context
    



class ProductView(DetailView):
    model = Item
    template_name = "product.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Récupérez l'utilisateur spécifique (par exemple, l'utilisateur connecté)
        user = self.request.user
        
        # Récupérez l'utilisateur spécifique (par exemple, l'utilisateur avec l'ID 1)
       
        # Récupérez les badges associés à cet utilisateur
        badges = user.badge_set.all()
        
        # Ajoutez les badges au contexte de la vue
        context['user_badges'] = badges
        
        return context
    
    def track_product_click(request, pk, **kwargs):
        # Récupérez le produit à partir de la base de données
        product = get_object_or_404(Item, pk=pk)

        # Vérifiez si l'utilisateur a déjà cliqué sur ce produit dans la session
        clicked_products = request.session.get('clicked_products', [])
        if pk not in clicked_products:
            # Incrémentation de la valeur views
            product.views += 1
            if product.views >=1000:
                badge = Badge(user=product.user, label="Start")
                badge.save()

            product.save()
            # Enregistrez ce produit comme "clic" dans la session
            clicked_products.append(pk)
            request.session['clicked_products'] = clicked_products
          
            
        
        # Redirigez l'utilisateur vers la vue détaillée du produit
        return redirect(product.get_absolute_url())
   

class OrderSummaryView(LoginRequiredMixin, View):
    def get(self, *args, **kwargs):

        try:
            order = Order.objects.get(user=self.request.user, ordered=False)
            context = {
                'object': order
            }
            return render(self.request, 'order_summary.html', context)
        except ObjectDoesNotExist:
            messages.error(self.request, "You do not have an order")
            return redirect("/")

class CheckoutView(View):
    def get(self, *args, **kwargs):
        form = CheckoutForm()
        order = Order.objects.get(user=self.request.user, ordered=False)
        context = {
            'form': form,
            'order': order
        }
        return render(self.request, 'checkout.html', context)

    def post(self, *args, **kwargs):
        form = CheckoutForm(self.request.POST or None)
        
        try:
            order = Order.objects.get(user=self.request.user, ordered=False)
            if form.is_valid():
                street_address = form.cleaned_data.get('street_address')
                apartment_address = form.cleaned_data.get('apartment_address')
                country = form.cleaned_data.get('country')
                zip = form.cleaned_data.get('zip')
                # TODO: add functionaly for these fields
                # same_billing_address = form.cleaned_data.get('same_billing_address')
                # save_info = form.cleaned_data.get('save_info')
                payment_option = form.cleaned_data.get('payment_option')

                checkout_address = CheckoutAddress(
                    user=self.request.user,
                    street_address=street_address,
                    apartment_address=apartment_address,
                    country=country,
                    zip=zip
                )
                checkout_address.save()
                order.checkout_address = checkout_address
                order.save()

                if payment_option == 'S':
                    return redirect('core:payment', payment_option='stripe')
                elif payment_option == 'P':
                    return redirect('core:payment', payment_option='paypal')
                else:
                    messages.warning(self.request, "Invalid Payment option")
                    return redirect('core:checkout')

        except ObjectDoesNotExist:
            messages.error(self.request, "You do not have an order")
            return redirect("core:order-summary")

class PaymentView(View):
    def get(self, *args, **kwargs):
        order = Order.objects.get(user=self.request.user, ordered=False)
        context = {
            'order': order
        }
        return render(self.request, "payment.html", context)

    def post(self, *args, **kwargs):
        order = Order.objects.get(user=self.request.user, ordered=False)
        token = self.request.POST.get('stripeToken')
        amount = int(order.get_total_price() * 100)  #cents

        try:
            charge = stripe.Charge.create(
                amount=amount,
                currency="usd",
                source=token
            )

            # create payment
            payment = Payment()
            payment.stripe_id = charge['id']
            payment.user = self.request.user
            payment.amount = order.get_total_price()
            payment.save()

            # assign payment to order
            order.ordered = True
            order.payment = payment
            order.save()

            messages.success(self.request, "Success make an order")
            return redirect('/')

        except stripe.error.CardError as e:
            body = e.json_body
            err = body.get('error', {})
            messages.error(self.request, f"{err.get('message')}")
            return redirect('/')

        except stripe.error.RateLimitError as e:
            # Too many requests made to the API too quickly
            messages.error(self.request, "To many request error")
            return redirect('/')

        except stripe.error.InvalidRequestError as e:
            # Invalid parameters were supplied to Stripe's API
            messages.error(self.request, "Invalid Parameter")
            return redirect('/')

        except stripe.error.AuthenticationError as e:
            # Authentication with Stripe's API failed
            # (maybe you changed API keys recently)
            messages.error(self.request, "Authentication with stripe failed")
            return redirect('/')

        except stripe.error.APIConnectionError as e:
            # Network communication with Stripe failed
            messages.error(self.request, "Network Error")
            return redirect('/')

        except stripe.error.StripeError as e:
            # Display a very generic error to the user, and maybe send
            # yourself an email
            messages.error(self.request, "Something went wrong")
            return redirect('/')
        
        except Exception as e:
            # Something else happened, completely unrelated to Stripe
            messages.error(self.request, "Not identified error")
            return redirect('/')

        

        

@login_required
def add_to_cart(request, pk):
    item = get_object_or_404(Item, pk=pk )
    order_item, created = OrderItem.objects.get_or_create(
        item = item,
        user = request.user,
        ordered = False
    )
    order_qs = Order.objects.filter(user=request.user, ordered=False)

    if order_qs.exists():
        order = order_qs[0]

        if order.items.filter(item__pk=item.pk).exists():
            order_item.quantity += 1
            order_item.save()
            messages.info(request, "Added quantity Item")
            return redirect("core:order-summary")
        else:
            order.items.add(order_item)
            messages.info(request, "Item added to your cart")
            return redirect("core:order-summary")
    else:
        ordered_date = timezone.now()
        order = Order.objects.create(user=request.user, ordered_date=ordered_date)
        order.items.add(order_item)
        messages.info(request, "Item added to your cart")
        return redirect("core:order-summary")

@login_required
def remove_from_cart(request, pk):
    item = get_object_or_404(Item, pk=pk )
    order_qs = Order.objects.filter(
        user=request.user, 
        ordered=False
    )
    if order_qs.exists():
        order = order_qs[0]
        if order.items.filter(item__pk=item.pk).exists():
            order_item = OrderItem.objects.filter(
                item=item,
                user=request.user,
                ordered=False
            )[0]
            order_item.delete()
            messages.info(request, "Item \""+order_item.item.item_name+"\" remove from your cart")
            return redirect("core:order-summary")
        else:
            messages.info(request, "This Item not in your cart")
            return redirect("core:product", pk=pk)
    else:
        #add message doesnt have order
        messages.info(request, "You do not have an Order")
        return redirect("core:product", pk = pk)


@login_required
def reduce_quantity_item(request, pk):
    item = get_object_or_404(Item, pk=pk )
    order_qs = Order.objects.filter(
        user = request.user, 
        ordered = False
    )
    if order_qs.exists():
        order = order_qs[0]
        if order.items.filter(item__pk=item.pk).exists() :
            order_item = OrderItem.objects.filter(
                item = item,
                user = request.user,
                ordered = False
            )[0]
            if order_item.quantity > 1:
                order_item.quantity -= 1
                order_item.save()
            else:
                order_item.delete()
            messages.info(request, "Item quantity was updated")
            return redirect("core:order-summary")
        else:
            messages.info(request, "This Item not in your cart")
            return redirect("core:order-summary")
    else:
        #add message doesnt have order
        messages.info(request, "You do not have an Order")
        return redirect("core:order-summary")


class UploadView(View):
    def upload_zip(request):
        if request.method == 'POST':
            
            form = UploadFileForm(request.POST, request.FILES)
            if form.is_valid():
                id = request.user
                uploaded_file = form.save()

                zip_file = uploaded_file.file.path
                extract_path = os.path.join('media/extracted', str(id))

            
    
                # Créez le répertoire d'extraction s'il n'existe pas
                os.makedirs(extract_path, exist_ok=True)

                # Extrayez le contenu du fichier ZIP
                with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                    zip_ref.extractall(extract_path)
                

                return redirect('success')
        else:
            form = UploadFileForm()
        return render(request, 'upload.html', {'form': form})

    def success(request):
        return render(request, 'success.html')
    
class AddProduct(View):
    
    
    @login_required
    def addProduct(request):
        if request.method == 'POST':
            form = AddProductForm(request.POST, request.FILES)
            if form.is_valid():
                
                item = form.save(commit=False)  # Utilisez commit=False pour éviter la sauvegarde immédiate
                item.user = request.user  # Associez l'utilisateur actuel à l'objet Item

                # Enregistrez maintenant l'objet Item avec l'utilisateur associé
                item.save()
                nombre_produits = Item.objects.filter(user=request.user).count()
                existing_badge = Badge.objects.filter(user=request.user, label="Collector").first()
                if not existing_badge:
                    if nombre_produits >=5:
                        badge = Badge(user=request.user, label="Collector")
                        badge.save()

                # Vous pouvez maintenant accéder au chemin du fichier comme ceci
                zip_file = item.file.path
                extract_path = os.path.join('media/extracted', str(item.id))

            
    
                # Créez le répertoire d'extraction s'il n'existe pas
                os.makedirs(extract_path, exist_ok=True)

                # Extrayez le contenu du fichier ZIP
                with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                    zip_ref.extractall(extract_path)

    
                

                return redirect('success')
        else:
            form = AddProductForm()
        return render(request, 'add_product.html', {'form': form})
    def success(request):
        return render(request, 'success.html')
    


class UserBadgeList(generics.ListAPIView):
    serializer_class = BadgeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user_id = self.kwargs['user_id']  # Récupérez l'ID de l'utilisateur depuis les paramètres d'URL
        return Badge.objects.filter(user_id=user_id)