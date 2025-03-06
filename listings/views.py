from django.shortcuts import render
from . models import Listing
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

# Create your views here.
def listings(request):
  #listings = Listing.objects.all()
  listings = Listing.objects.order_by('-list_date').filter(is_published=True)
  paginator = Paginator(listings, 3)
  page = request.GET.get('page')
  paged_listings = paginator.get_page(page)
  context = {'listings':paged_listings}
  #context = {'listings':listings}
  return render(request, 'listings/listings.html', context)
  # return render(request, 'listings/listings.html',{'listings':'something'})

def listing(request,listing_id):
  return render(request, 'listings/listing.html')

def search(request):
  return render(request,'listings/search.html')